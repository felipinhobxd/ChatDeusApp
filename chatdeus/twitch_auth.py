from __future__ import annotations

from dataclasses import dataclass
import logging
import threading
import time
from typing import Callable
import webbrowser

import requests

from .config import AppConfig, save_config

log = logging.getLogger(__name__)

# Client ID público da aplicação ChatDeusApp SindromeGames.
# Client IDs são públicos por definição; nunca embutimos Client Secret no executável.
TWITCH_CLIENT_ID = "urssznt1hesprr4qeku0ees5w8rzsq"
TWITCH_SCOPES = ("user:read:chat",)
TWITCH_SCOPE_STRING = " ".join(TWITCH_SCOPES)
DEVICE_URL = "https://id.twitch.tv/oauth2/device"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
REVOKE_URL = "https://id.twitch.tv/oauth2/revoke"


class TwitchAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthSession:
    access_token: str
    client_id: str
    user_id: str
    login: str
    scopes: tuple[str, ...]
    expires_in: int
    refreshed: bool = False


class TwitchAuthManager:
    """OAuth público da Twitch com Device Code Flow e refresh automático."""

    def __init__(
        self,
        config: AppConfig,
        on_status: Callable[[dict], None] | None = None,
        save_func: Callable[[AppConfig], object] = save_config,
    ):
        self.config = config
        self.on_status = on_status
        self._save = save_func
        self._lock = threading.RLock()
        self._login_thread: threading.Thread | None = None
        self._cancel_login = threading.Event()
        self._pending = False
        self._last_error = ""
        self._verification_uri = ""
        self._user_code = ""

    def update_config(self, config: AppConfig) -> None:
        with self._lock:
            self.config = config

    @property
    def has_managed_credentials(self) -> bool:
        return bool(self.config.twitch_access_token or self.config.twitch_refresh_token)

    @property
    def pending(self) -> bool:
        with self._lock:
            return self._pending

    @property
    def verification_uri(self) -> str:
        with self._lock:
            return self._verification_uri

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "pending": self._pending,
                "connected": bool(self.config.twitch_access_token and self.config.twitch_user_id),
                "login": self.config.twitch_login,
                "channel": self.config.twitch_channel,
                "user_code": self._user_code,
                "verification_uri": self._verification_uri,
                "error": self._last_error,
            }

    def _emit(self, state: str, **extra) -> None:
        payload = {"state": state, **self.snapshot(), **extra}
        callback = self.on_status
        if callback:
            try:
                callback(payload)
            except Exception:
                log.exception("Falha no callback de status OAuth da Twitch.")

    def begin_device_login(self) -> bool:
        with self._lock:
            if self._login_thread and self._login_thread.is_alive():
                return False
            self._cancel_login = threading.Event()
            self._pending = True
            self._last_error = ""
            self._verification_uri = ""
            self._user_code = ""
            self._login_thread = threading.Thread(
                target=self._device_login_worker,
                name="chatdeus-twitch-login",
                daemon=True,
            )
            self._login_thread.start()
        self._emit("requesting")
        return True

    def cancel_login(self) -> None:
        self._cancel_login.set()

    def _device_login_worker(self) -> None:
        try:
            response = requests.post(
                DEVICE_URL,
                data={"client_id": TWITCH_CLIENT_ID, "scopes": TWITCH_SCOPE_STRING},
                timeout=15,
            )
            data = self._json_or_error(response, "Não foi possível iniciar o login da Twitch.")
            device_code = str(data.get("device_code", ""))
            user_code = str(data.get("user_code", ""))
            verification_uri = str(data.get("verification_uri", ""))
            expires_in = max(30, int(data.get("expires_in", 1800)))
            interval = max(1, int(data.get("interval", 5)))
            if not device_code or not verification_uri:
                raise TwitchAuthError("A Twitch não retornou um código de autorização válido.")

            with self._lock:
                self._verification_uri = verification_uri
                self._user_code = user_code
            self._emit("waiting")
            try:
                webbrowser.open(verification_uri)
            except Exception:
                log.exception("Não foi possível abrir o navegador automaticamente.")

            deadline = time.monotonic() + expires_in
            while time.monotonic() < deadline and not self._cancel_login.is_set():
                token_response = requests.post(
                    TOKEN_URL,
                    data={
                        "client_id": TWITCH_CLIENT_ID,
                        "scopes": TWITCH_SCOPE_STRING,
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    timeout=15,
                )
                if token_response.status_code == 200:
                    token_data = token_response.json()
                    self._store_tokens(token_data)
                    session = self.ensure_valid()
                    if not session:
                        raise TwitchAuthError("A autorização terminou, mas o token não pôde ser validado.")
                    with self._lock:
                        self._pending = False
                        self._last_error = ""
                    self._emit("connected", login=session.login)
                    return

                payload = self._safe_json(token_response)
                message = str(payload.get("message", "")).lower()
                if "authorization_pending" in message:
                    time.sleep(interval)
                    continue
                if "slow_down" in message:
                    interval += 5
                    time.sleep(interval)
                    continue
                if token_response.status_code in {400, 401}:
                    raise TwitchAuthError(payload.get("message") or "A autorização da Twitch foi recusada ou expirou.")
                token_response.raise_for_status()

            if self._cancel_login.is_set():
                raise TwitchAuthError("Login cancelado.")
            raise TwitchAuthError("O código da Twitch expirou. Clique em Entrar com Twitch novamente.")
        except Exception as exc:
            message = str(exc) or "Falha desconhecida no login da Twitch."
            with self._lock:
                self._pending = False
                self._last_error = message
            log.warning("Login Twitch falhou: %s", message)
            self._emit("error", error=message)

    def ensure_valid(self) -> AuthSession | None:
        """Valida o token; se estiver inválido, tenta refresh uma única vez."""
        with self._lock:
            token = self.config.twitch_access_token.strip()
            refresh_token = self.config.twitch_refresh_token.strip()
        if not token:
            if refresh_token:
                self._refresh_access_token()
                token = self.config.twitch_access_token.strip()
            else:
                return None

        response = requests.get(
            VALIDATE_URL,
            headers={"Authorization": f"OAuth {token}"},
            timeout=15,
        )
        refreshed = False
        if response.status_code == 401 and refresh_token:
            self._refresh_access_token()
            refreshed = True
            token = self.config.twitch_access_token.strip()
            response = requests.get(
                VALIDATE_URL,
                headers={"Authorization": f"OAuth {token}"},
                timeout=15,
            )

        if response.status_code != 200:
            if response.status_code == 401:
                raise TwitchAuthError("Sua sessão da Twitch expirou. Entre com a Twitch novamente.")
            response.raise_for_status()

        data = response.json()
        scopes = tuple(sorted(str(scope) for scope in data.get("scopes", [])))
        missing = sorted(set(TWITCH_SCOPES) - set(scopes))
        if missing:
            raise TwitchAuthError(
                "A autorização da Twitch não possui a permissão necessária: " + ", ".join(missing)
            )

        login = str(data.get("login", "")).strip().lower()
        user_id = str(data.get("user_id", "")).strip()
        client_id = str(data.get("client_id", "")).strip()
        if not login or not user_id or not client_id:
            raise TwitchAuthError("A Twitch validou o token, mas não informou a conta conectada.")

        with self._lock:
            self.config.twitch_access_token = token
            self.config.twitch_user_id = user_id
            self.config.twitch_login = login
            self.config.twitch_channel = login
            self.config.twitch_token_client_id = client_id
            self.config.twitch_scopes = list(scopes)
            self.config.twitch_manual_mode = False
            self._save(self.config)

        return AuthSession(
            access_token=token,
            client_id=client_id,
            user_id=user_id,
            login=login,
            scopes=scopes,
            expires_in=int(data.get("expires_in", 0) or 0),
            refreshed=refreshed,
        )

    def _refresh_access_token(self) -> None:
        with self._lock:
            refresh_token = self.config.twitch_refresh_token.strip()
        if not refresh_token:
            raise TwitchAuthError("Não há refresh token salvo. Entre com a Twitch novamente.")
        response = requests.post(
            TOKEN_URL,
            data={
                "client_id": TWITCH_CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=15,
        )
        data = self._json_or_error(response, "Não foi possível renovar a sessão da Twitch.")
        self._store_tokens(data, previous_refresh=refresh_token)
        log.info("Token da Twitch renovado automaticamente.")

    def _store_tokens(self, data: dict, previous_refresh: str = "") -> None:
        access = str(data.get("access_token", "")).strip()
        refresh = str(data.get("refresh_token", "") or previous_refresh).strip()
        if not access:
            raise TwitchAuthError("A Twitch não retornou um access token.")
        with self._lock:
            self.config.twitch_access_token = access
            self.config.twitch_refresh_token = refresh
            self.config.twitch_token_client_id = TWITCH_CLIENT_ID
            self.config.twitch_scopes = [str(scope) for scope in data.get("scope", TWITCH_SCOPES)]
            self.config.twitch_manual_mode = False
            self._save(self.config)

    def disconnect(self) -> None:
        self.cancel_login()
        with self._lock:
            token = self.config.twitch_access_token.strip()
            client_id = self.config.twitch_token_client_id.strip() or TWITCH_CLIENT_ID
        if token:
            try:
                requests.post(REVOKE_URL, data={"client_id": client_id, "token": token}, timeout=10)
            except Exception:
                log.debug("Não foi possível revogar o token remotamente; removendo credenciais locais.", exc_info=True)
        with self._lock:
            self.config.twitch_access_token = ""
            self.config.twitch_refresh_token = ""
            self.config.twitch_user_id = ""
            self.config.twitch_login = ""
            self.config.twitch_token_client_id = ""
            self.config.twitch_scopes = []
            self._pending = False
            self._verification_uri = ""
            self._user_code = ""
            self._last_error = ""
            self._save(self.config)
        self._emit("disconnected")

    @staticmethod
    def _safe_json(response) -> dict:
        try:
            data = response.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @classmethod
    def _json_or_error(cls, response, fallback: str) -> dict:
        data = cls._safe_json(response)
        if response.status_code >= 400:
            raise TwitchAuthError(str(data.get("message") or data.get("error") or fallback))
        return data
