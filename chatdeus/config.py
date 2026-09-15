from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import shutil
from typing import Any


def _config_dir() -> Path:
    if os.name == "nt":
        base = os.getenv("APPDATA") or os.path.expanduser("~")
        return Path(base) / "ChatDeusApp"
    xdg = os.getenv("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "chatdeusapp"
    return Path.home() / ".config" / "chatdeusapp"


CONFIG_DIR = _config_dir()
CONFIG_PATH = CONFIG_DIR / "config.json"
CHARACTER_DIR = CONFIG_DIR / "characters"
ALLOWED_CHARACTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
CHARACTER_MAX_BYTES = 25 * 1024 * 1024
IDLE_ANIMATIONS = {"none", "float", "breathe"}
SPEAKING_ANIMATIONS = {"auto", "bounce", "shake", "pulse", "talk", "none"}


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

    character_image_1: str = ""
    character_image_2: str = ""
    character_image_3: str = ""
    character_size_1: int = 320
    character_size_2: int = 320
    character_size_3: int = 320
    character_intensity_1: int = 5
    character_intensity_2: int = 5
    character_intensity_3: int = 5
    character_x_1: int = 0
    character_x_2: int = 0
    character_x_3: int = 0
    character_y_1: int = 0
    character_y_2: int = 0
    character_y_3: int = 0
    character_mirror_1: bool = False
    character_mirror_2: bool = False
    character_mirror_3: bool = False
    character_idle_1: str = "float"
    character_idle_2: str = "float"
    character_idle_3: str = "float"
    character_speaking_1: str = "auto"
    character_speaking_2: str = "auto"
    character_speaking_3: str = "auto"

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

        commands = [self.command_player_1.strip(), self.command_player_2.strip(), self.command_player_3.strip()]
        defaults = ["!jogador1", "!jogador2", "!jogador3"]
        self.command_player_1, self.command_player_2, self.command_player_3 = [
            command or defaults[index] for index, command in enumerate(commands)
        ]

        for player in (1, 2, 3):
            image_key = f"character_image_{player}"
            image_name = str(getattr(self, image_key, "")).strip()
            setattr(self, image_key, Path(image_name).name if image_name else "")

            size_key = f"character_size_{player}"
            intensity_key = f"character_intensity_{player}"
            x_key = f"character_x_{player}"
            y_key = f"character_y_{player}"
            setattr(self, size_key, max(80, min(int(getattr(self, size_key)), 800)))
            setattr(self, intensity_key, max(0, min(int(getattr(self, intensity_key)), 10)))
            setattr(self, x_key, max(-1000, min(int(getattr(self, x_key)), 1000)))
            setattr(self, y_key, max(-1000, min(int(getattr(self, y_key)), 1000)))

            idle_key = f"character_idle_{player}"
            idle = str(getattr(self, idle_key)).strip().lower()
            setattr(self, idle_key, idle if idle in IDLE_ANIMATIONS else "float")

            speaking_key = f"character_speaking_{player}"
            speaking = str(getattr(self, speaking_key)).strip().lower()
            setattr(self, speaking_key, speaking if speaking in SPEAKING_ANIMATIONS else "auto")

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


def character_file_path(config: AppConfig, player: int) -> Path | None:
    if player not in (1, 2, 3):
        return None
    name = Path(str(getattr(config, f"character_image_{player}", ""))).name
    if not name:
        return None
    path = CHARACTER_DIR / name
    return path if path.is_file() else None


def install_character_image(player: int, source: str | Path) -> str:
    if player not in (1, 2, 3):
        raise ValueError("Jogador inválido.")
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise ValueError("A imagem escolhida não existe.")
    suffix = source_path.suffix.lower()
    if suffix not in ALLOWED_CHARACTER_EXTENSIONS:
        raise ValueError("Use PNG, JPG, JPEG, WebP ou GIF.")
    if source_path.stat().st_size > CHARACTER_MAX_BYTES:
        raise ValueError("A imagem deve ter no máximo 25 MB.")

    CHARACTER_DIR.mkdir(parents=True, exist_ok=True)
    for old in CHARACTER_DIR.glob(f"jogador{player}.*"):
        try:
            old.unlink()
        except OSError:
            pass
    target = CHARACTER_DIR / f"jogador{player}{suffix}"
    shutil.copy2(source_path, target)
    return target.name


def remove_character_image(player: int) -> None:
    if player not in (1, 2, 3):
        return
    if not CHARACTER_DIR.exists():
        return
    for old in CHARACTER_DIR.glob(f"jogador{player}.*"):
        try:
            old.unlink()
        except OSError:
            pass


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
