from __future__ import annotations

import logging
from pathlib import Path
import threading
import webbrowser

from .audio import AudioWorker
from .config import AppConfig, character_file_path
from .obs import OBSManager
from .state import PlayerManager
from .tts import TTSManager
from .twitch_auth import TwitchAuthManager
from .twitch_service import TwitchService
from .web import create_app

log = logging.getLogger(__name__)

TWITCH_FIELDS = [
    "twitch_access_token",
    "twitch_refresh_token",
    "twitch_user_id",
    "twitch_login",
    "twitch_token_client_id",
    "twitch_scopes",
    "twitch_manual_mode",
    "twitch_channel",
    "twitch_token",
]


class Runtime:
    def __init__(self, config: AppConfig):
        self.config = config.normalized()
        self._change_condition = threading.Condition()
        self._state_version = 0

        self.state = PlayerManager(self.config)
        self.state.on_change = self.signal_state_change
        self.tts = TTSManager(self.config)
        self.obs = OBSManager(self.config)
        self.audio = AudioWorker(
            self.tts,
            self.state,
            before_play=self._before_play,
            after_play=self._after_play,
        )
        self.state.on_selected_message = self.audio.enqueue

        self.twitch_auth = TwitchAuthManager(self.config)
        self.twitch = TwitchService(self.config, self.state, self.twitch_auth)
        self.flask_app = create_app(self)
        self.web_thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        visible_host = "127.0.0.1" if self.config.web_host in {"0.0.0.0", "::"} else self.config.web_host
        return f"http://{visible_host}:{self.config.web_port}"

    def _before_play(self, player: int) -> None:
        self.state.set_speaking(player, True)
        self.obs.set_player_active(player, True)

    def _after_play(self, player: int) -> None:
        self.obs.set_player_active(player, False)
        self.state.set_speaking(player, False)

    def signal_state_change(self) -> None:
        with self._change_condition:
            self._state_version += 1
            self._change_condition.notify_all()

    def wait_for_change(self, after_version: int, timeout: float = 15.0) -> int:
        with self._change_condition:
            if self._state_version <= after_version:
                self._change_condition.wait(timeout=timeout)
            return self._state_version

    def character_file(self, player: int) -> Path | None:
        return character_file_path(self.config, player)

    def character_public(self, player: int) -> dict:
        path = self.character_file(player)
        version = path.stat().st_mtime_ns if path else 0
        return {
            "configured": bool(path),
            "url": f"/character/{player}?v={version}" if path else "",
            "size": getattr(self.config, f"character_size_{player}"),
            "intensity": getattr(self.config, f"character_intensity_{player}"),
            "x": getattr(self.config, f"character_x_{player}"),
            "y": getattr(self.config, f"character_y_{player}"),
            "mirror": getattr(self.config, f"character_mirror_{player}"),
            "idle": getattr(self.config, f"character_idle_{player}"),
            "speaking": getattr(self.config, f"character_speaking_{player}"),
        }

    def apply_visual_config(self, updated: AppConfig) -> None:
        updated.normalized()
        fields = ["command_player_1", "command_player_2", "command_player_3"]
        for player in (1, 2, 3):
            fields.extend(
                [
                    f"character_image_{player}",
                    f"character_size_{player}",
                    f"character_intensity_{player}",
                    f"character_x_{player}",
                    f"character_y_{player}",
                    f"character_mirror_{player}",
                    f"character_idle_{player}",
                    f"character_speaking_{player}",
                ]
            )
        for field in fields:
            setattr(self.config, field, getattr(updated, field))
        self.state.config = self.config
        self.signal_state_change()

    def apply_connection_config(self, updated: AppConfig) -> None:
        updated.normalized()
        before = tuple(repr(getattr(self.config, field)) for field in TWITCH_FIELDS)
        for field in TWITCH_FIELDS:
            value = getattr(updated, field)
            setattr(self.config, field, list(value) if isinstance(value, list) else value)
        after = tuple(repr(getattr(self.config, field)) for field in TWITCH_FIELDS)
        self.twitch.update_config(self.config)
        if before != after:
            if self.twitch.thread and self.twitch.thread.is_alive():
                self.twitch.restart()
            else:
                self.twitch.start()
        self.signal_state_change()

    def start(self) -> None:
        self.audio.start()
        self.twitch.start()
        if not self.web_thread or not self.web_thread.is_alive():
            self.web_thread = threading.Thread(target=self._run_web, name="chatdeus-web", daemon=True)
            self.web_thread.start()

    def _run_web(self) -> None:
        self.flask_app.run(
            host=self.config.web_host,
            port=self.config.web_port,
            threaded=True,
            use_reloader=False,
        )

    def open_panel(self) -> None:
        webbrowser.open(self.base_url)
