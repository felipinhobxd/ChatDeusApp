from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from typing import Any


def _config_dir() -> Path:
    """Retorna uma pasta gravável adequada para configurações do usuário."""
    if os.name == "nt":
        base = os.getenv("APPDATA") or os.path.expanduser("~")
        return Path(base) / "ChatDeusApp"
    xdg = os.getenv("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "chatdeusapp"
    return Path.home() / ".config" / "chatdeusapp"


CONFIG_DIR = _config_dir()
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass
class AppConfig:
    twitch_channel: str = ""
    twitch_token: str = ""
    command_player_1: str = "!jogador1"
    command_player_2: str = "!jogador2"
    command_player_3: str = "!jogador3"
    activity_seconds: int = 450
    max_pool_users: int = 2000

    azure_key: str = ""
    azure_region: str = ""
    azure_enabled: bool = True
    fallback_gtts: bool = True
    default_voice_1: str = "pt-BR-AntonioNeural"
    default_voice_2: str = "pt-BR-FranciscaNeural"
    default_voice_3: str = "pt-BR-ThalitaNeural"

    obs_enabled: bool = False
    obs_host: str = "127.0.0.1"
    obs_port: int = 4455
    obs_password: str = ""
    obs_source: str = ""
    obs_filter_1: str = ""
    obs_filter_2: str = ""
    obs_filter_3: str = ""

    web_host: str = "127.0.0.1"
    web_port: int = 5000
    open_panel_on_start: bool = True

    extra: dict[str, Any] = field(default_factory=dict, repr=False)

    def normalized(self) -> "AppConfig":
        self.twitch_channel = self.twitch_channel.strip().lstrip("#").lower()
        self.twitch_token = self.twitch_token.strip()
        self.azure_key = self.azure_key.strip()
        self.azure_region = self.azure_region.strip()
        self.obs_host = self.obs_host.strip() or "127.0.0.1"
        self.web_host = self.web_host.strip() or "127.0.0.1"

        self.activity_seconds = max(30, min(int(self.activity_seconds), 86_400))
        self.max_pool_users = max(10, min(int(self.max_pool_users), 50_000))
        self.obs_port = max(1, min(int(self.obs_port), 65_535))
        self.web_port = max(1, min(int(self.web_port), 65_535))

        commands = [
            self.command_player_1.strip(),
            self.command_player_2.strip(),
            self.command_player_3.strip(),
        ]
        defaults = ["!jogador1", "!jogador2", "!jogador3"]
        self.command_player_1, self.command_player_2, self.command_player_3 = [
            command or defaults[index] for index, command in enumerate(commands)
        ]
        return self

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        extra = data.pop("extra", {})
        data.update(extra)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        known = set(cls.__dataclass_fields__.keys()) - {"extra"}
        values = {key: data[key] for key in known if key in data}
        extra = {key: value for key, value in data.items() if key not in known}
        cfg = cls(**values)
        cfg.extra = extra
        return cfg.normalized()


def load_config(path: Path | None = None) -> AppConfig:
    target = path or CONFIG_PATH
    if not target.exists():
        return AppConfig()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("configuração inválida")
        return AppConfig.from_dict(data)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return AppConfig()


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    target = path or CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    payload = json.dumps(config.normalized().to_dict(), ensure_ascii=False, indent=2)
    temp.write_text(payload + "\n", encoding="utf-8")
    temp.replace(target)
    return target
