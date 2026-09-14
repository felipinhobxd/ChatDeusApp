from __future__ import annotations

import logging
import threading
import webbrowser

from .audio import AudioWorker
from .config import AppConfig
from .obs import OBSManager
from .state import PlayerManager
from .tts import TTSManager
from .twitch_service import TwitchService
from .web import create_app

log = logging.getLogger(__name__)


class Runtime:
    def __init__(self, config: AppConfig):
        self.config = config.normalized()
        self.state = PlayerManager(self.config)
        self.tts = TTSManager(self.config)
        self.obs = OBSManager(self.config)
        self.audio = AudioWorker(self.tts, self.state, before_play=lambda player: self.obs.set_player_active(player, True), after_play=lambda player: self.obs.set_player_active(player, False))
        self.state.on_selected_message = self.audio.enqueue
        self.twitch = TwitchService(self.config, self.state)
        self.flask_app = create_app(self)
        self.web_thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        visible_host = "127.0.0.1" if self.config.web_host in {"0.0.0.0", "::"} else self.config.web_host
        return f"http://{visible_host}:{self.config.web_port}"

    def start(self) -> None:
        self.audio.start()
        self.twitch.start()
        if not self.web_thread or not self.web_thread.is_alive():
            self.web_thread = threading.Thread(target=self._run_web, name="chatdeus-web", daemon=True)
            self.web_thread.start()

    def _run_web(self) -> None:
        self.flask_app.run(host=self.config.web_host, port=self.config.web_port, threaded=True, use_reloader=False)

    def open_panel(self) -> None:
        webbrowser.open(self.base_url)
