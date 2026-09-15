from __future__ import annotations

from collections import deque
import asyncio
import json
import logging
import threading
import time
from urllib.parse import urlencode

import requests
import websocket

from .config import AppConfig
from .state import PlayerManager
from .twitch_auth import AuthSession, TwitchAuthError, TwitchAuthManager

log = logging.getLogger(__name__)

EVENTSUB_WS_URL = "wss://eventsub.wss.twitch.tv/ws?keepalive_timeout_seconds=30"
EVENTSUB_SUBSCRIPTIONS_URL = "https://api.twitch.tv/helix/eventsub/subscriptions"
HELIX_USERS_URL = "https://api.twitch.tv/helix/users"


class TwitchService:
    """Leitura do chat via EventSub WebSocket, com fallback legado via TwitchIO."""

    def __init__(self, config: AppConfig, state: PlayerManager, auth: TwitchAuthManager | None = None):
        self.config = config
        self.state = state
        self.auth = auth or TwitchAuthManager(config)
        self.thread: threading.Thread | None = None
        self.ready = threading.Event()
        self.error = ""
        self.mode = "none"
        self.channel = ""
        self.bot = None
        self._stop_event = threading.Event()
        self._ws = None
        self._recent_message_ids: deque[str] = deque(maxlen=300)
        self._recent_message_set: set[str] = set()
        self._lock = threading.RLock()

    @property
    def manual_active(self) -> bool:
        return bool(
            self.config.twitch_manual_mode
            and self.config.twitch_channel
            and self.config.twitch_token
        )

    @property
    def configured(self) -> bool:
        if self.manual_active:
            return bool(self.config.twitch_channel and self.config.twitch_token)
        return self.auth.has_managed_credentials

    def public_status(self) -> dict:
        auth_status = self.auth.snapshot()
        return {
            "configured": self.configured,
            "ready": self.ready.is_set(),
            "error": self.error,
            "mode": self.mode,
            "login": self.config.twitch_login or auth_status.get("login", ""),
            "channel": self.channel or self.config.twitch_channel,
            "auth_pending": auth_status.get("pending", False),
        }

    def update_config(self, config: AppConfig) -> None:
        with self._lock:
            self.config = config
            self.auth.update_config(config)

    def start(self) -> bool:
        if not self.configured:
            log.info("Twitch ainda não conectada. Use 'Entrar com Twitch' no aplicativo.")
            return False
        if self.thread and self.thread.is_alive():
            return True
        self._stop_event = threading.Event()
        self.error = ""
        self.thread = threading.Thread(
            target=self._thread_main,
            args=(self._stop_event,),
            name="chatdeus-twitch",
            daemon=True,
        )
        self.thread.start()
        return True

    def stop(self, timeout: float = 3.0) -> None:
        event = self._stop_event
        event.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        thread = self.thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        self.ready.clear()

    def restart(self) -> bool:
        if self.mode == "legacy" and self.thread and self.thread.is_alive():
            log.info("Modo manual ativo; reinicie o aplicativo para trocar de conexão Twitch.")
            return True
        self.stop()
        self.thread = None
        self.mode = "none"
        return self.start()

    def _thread_main(self, stop_event: threading.Event) -> None:
        try:
            if self.manual_active:
                self.mode = "legacy"
                self._run_legacy_twitchio()
            else:
                self.mode = "eventsub"
                self._run_eventsub(stop_event)
        except Exception as exc:
            self.ready.clear()
            self.error = str(exc)
            log.exception("Falha na conexão com a Twitch.")

    def _run_eventsub(self, stop_event: threading.Event) -> None:
        reconnect_url = EVENTSUB_WS_URL
        preserve_subscription = False
        retry_delay = 2.0

        while not stop_event.is_set():
            try:
                session = self.auth.ensure_valid()
                if not session:
                    raise TwitchAuthError("Entre com a Twitch antes de iniciar o chat.")
                channel = (self.config.twitch_channel or session.login).strip().lower()
                broadcaster_id = self._resolve_broadcaster_id(session, channel)
                self.channel = channel

                ws = websocket.create_connection(reconnect_url, timeout=35, enable_multithread=True)
                self._ws = ws
                welcome = self._recv_json(ws)
                if welcome.get("metadata", {}).get("message_type") != "session_welcome":
                    raise RuntimeError("A Twitch não enviou a confirmação inicial do EventSub.")
                socket_session_id = welcome.get("payload", {}).get("session", {}).get("id", "")
                if not socket_session_id:
                    raise RuntimeError("A Twitch não informou o ID da sessão WebSocket.")

                if not preserve_subscription:
                    self._create_chat_subscription(session, broadcaster_id, socket_session_id)

                self.ready.set()
                self.error = ""
                retry_delay = 2.0
                log.info("Twitch conectada via EventSub como @%s no canal @%s.", session.login, channel)

                next_validation = time.monotonic() + 3600
                reconnect_url = EVENTSUB_WS_URL
                preserve_subscription = False

                while not stop_event.is_set():
                    message = self._recv_json(ws)
                    message_type = message.get("metadata", {}).get("message_type", "")
                    if message_type == "notification":
                        self._handle_notification(message)
                    elif message_type == "session_reconnect":
                        new_url = message.get("payload", {}).get("session", {}).get("reconnect_url")
                        if new_url:
                            reconnect_url = new_url
                            preserve_subscription = True
                            break
                    elif message_type == "revocation":
                        status = message.get("payload", {}).get("subscription", {}).get("status", "revogada")
                        raise RuntimeError(f"A Twitch revogou a assinatura do chat: {status}")

                    if time.monotonic() >= next_validation:
                        previous_token = session.access_token
                        session = self.auth.ensure_valid() or session
                        next_validation = time.monotonic() + 3600
                        if session.access_token != previous_token:
                            reconnect_url = EVENTSUB_WS_URL
                            preserve_subscription = False
                            break

                try:
                    ws.close()
                except Exception:
                    pass
                self._ws = None
                self.ready.clear()
                if stop_event.is_set():
                    return
                continue

            except TwitchAuthError as exc:
                self.ready.clear()
                self.error = str(exc)
                log.warning("Autorização Twitch inválida: %s", exc)
                return
            except Exception as exc:
                self.ready.clear()
                self.error = str(exc)
                self._ws = None
                preserve_subscription = False
                reconnect_url = EVENTSUB_WS_URL
                if stop_event.is_set():
                    return
                log.warning("Conexão Twitch caiu; tentando novamente em %.0fs: %s", retry_delay, exc)
                stop_event.wait(retry_delay)
                retry_delay = min(retry_delay * 1.8, 30.0)

    @staticmethod
    def _recv_json(ws) -> dict:
        raw = ws.recv()
        if not raw:
            raise ConnectionError("A conexão WebSocket da Twitch foi encerrada.")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}

    def _resolve_broadcaster_id(self, session: AuthSession, channel: str) -> str:
        if channel == session.login:
            return session.user_id
        headers = {
            "Authorization": f"Bearer {session.access_token}",
            "Client-Id": session.client_id,
        }
        response = requests.get(
            f"{HELIX_USERS_URL}?{urlencode({'login': channel})}",
            headers=headers,
            timeout=15,
        )
        if response.status_code == 401:
            refreshed = self.auth.ensure_valid()
            if refreshed:
                headers = {
                    "Authorization": f"Bearer {refreshed.access_token}",
                    "Client-Id": refreshed.client_id,
                }
                response = requests.get(
                    f"{HELIX_USERS_URL}?{urlencode({'login': channel})}",
                    headers=headers,
                    timeout=15,
                )
        response.raise_for_status()
        users = response.json().get("data", [])
        if not users:
            raise RuntimeError(f"Canal Twitch '@{channel}' não encontrado.")
        return str(users[0]["id"])

    def _create_chat_subscription(self, session: AuthSession, broadcaster_id: str, session_id: str) -> None:
        payload = {
            "type": "channel.chat.message",
            "version": "1",
            "condition": {
                "broadcaster_user_id": broadcaster_id,
                "user_id": session.user_id,
            },
            "transport": {"method": "websocket", "session_id": session_id},
        }
        response = requests.post(
            EVENTSUB_SUBSCRIPTIONS_URL,
            headers={
                "Authorization": f"Bearer {session.access_token}",
                "Client-Id": session.client_id,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        if response.status_code not in {200, 202}:
            try:
                detail = response.json().get("message", response.text)
            except Exception:
                detail = response.text
            raise RuntimeError(f"Não foi possível assinar o chat da Twitch ({response.status_code}): {detail}")

    @staticmethod
    def extract_chat_event(message: dict) -> tuple[str, str, str] | None:
        if message.get("metadata", {}).get("subscription_type") != "channel.chat.message":
            return None
        event = message.get("payload", {}).get("event", {})
        username = str(event.get("chatter_user_login") or event.get("chatter_user_name") or "").strip()
        text = str((event.get("message") or {}).get("text") or "").strip()
        message_id = str(event.get("message_id") or message.get("metadata", {}).get("message_id") or "")
        if not username or not text:
            return None
        return username, text, message_id

    def _handle_notification(self, message: dict) -> None:
        parsed = self.extract_chat_event(message)
        if not parsed:
            return
        username, text, message_id = parsed
        if message_id and message_id in self._recent_message_set:
            return
        if message_id:
            if len(self._recent_message_ids) == self._recent_message_ids.maxlen:
                old = self._recent_message_ids.popleft()
                self._recent_message_set.discard(old)
            self._recent_message_ids.append(message_id)
            self._recent_message_set.add(message_id)
        self.state.handle_chat_message(username=username, content=text)

    def _run_legacy_twitchio(self) -> None:
        """Compatibilidade com canal + token manual das versões 1.0/1.1."""
        from twitchio.ext import commands

        service = self

        class Bot(commands.Bot):
            def __init__(self):
                super().__init__(
                    token=service.config.twitch_token,
                    prefix="?",
                    initial_channels=[service.config.twitch_channel],
                )

            async def event_ready(self):
                service.ready.set()
                service.error = ""
                service.channel = service.config.twitch_channel
                log.info("Twitch conectada em modo manual como %s.", self.nick)

            async def event_message(self, message):
                if getattr(message, "echo", False):
                    return
                author = getattr(message, "author", None)
                if not author:
                    return
                username = getattr(author, "name", "") or getattr(author, "display_name", "")
                if username:
                    service.state.handle_chat_message(
                        username=username,
                        content=getattr(message, "content", "") or "",
                        timestamp=getattr(message, "timestamp", None),
                    )

        asyncio.set_event_loop(asyncio.new_event_loop())
        self.bot = Bot()
        self.bot.run()
