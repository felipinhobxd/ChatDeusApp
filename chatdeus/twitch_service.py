from __future__ import annotations

import asyncio
import logging
import threading

from .config import AppConfig
from .state import PlayerManager

log = logging.getLogger(__name__)


class TwitchService:
    def __init__(self, config: AppConfig, state: PlayerManager):
        self.config = config
        self.state = state
        self.bot = None
        self.thread: threading.Thread | None = None
        self.ready = threading.Event()
        self.error: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.config.twitch_channel and self.config.twitch_token)

    def start(self) -> bool:
        if not self.configured:
            log.info("Twitch não configurada; painel iniciado em modo local.")
            return False
        if self.thread and self.thread.is_alive():
            return True
        self.thread = threading.Thread(target=self._thread_main, name="chatdeus-twitch", daemon=True)
        self.thread.start()
        return True

    def _thread_main(self) -> None:
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
            self._run_bot()
        except Exception as exc:
            self.error = str(exc)
            log.exception("Falha ao iniciar conexão com Twitch.")

    def _run_bot(self) -> None:
        from twitchio.ext import commands
        service = self

        class Bot(commands.Bot):
            def __init__(self):
                super().__init__(token=service.config.twitch_token, prefix="?", initial_channels=[service.config.twitch_channel])

            async def event_ready(self):
                service.ready.set()
                log.info("Twitch conectada como %s.", self.nick)

            async def event_message(self, message):
                if getattr(message, "echo", False):
                    return
                author = getattr(message, "author", None)
                if not author:
                    return
                username = getattr(author, "name", "") or getattr(author, "display_name", "")
                if not username:
                    return
                service.state.handle_chat_message(username=username, content=getattr(message, "content", "") or "", timestamp=getattr(message, "timestamp", None))

        self.bot = Bot()
        self.bot.run()
