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
TTS_PROVIDERS = {"edge", "gtts", "azure"}
AUDIO_OUTPUTS = {"browser", "speakers"}
EDGE_PT_BR_VOICES = {"pt-BR-AntonioNeural", "pt-BR-FranciscaNeural"}


@dataclass
class AppConfig:
    twitch_access_token: str = ""
    twitch_refresh_token: str = ""
    twitch_user_id: str = ""
    twitch_login: str = ""
    twitch_token_client_id: str = ""
    twitch_scopes: list[str] = field(default_factory=list)
    twitch_manual_mode: bool = False
    twitch_channel: str = ""
    twitch_token: str = ""

    active_players: int = 3
    command_player_1: str = "!jogador1"
    command_player_2: str = "!jogador2"
    command_player_3: str = "!jogador3"
    activity_seconds: int = 450
    max_pool_users: int = 2000

    tts_provider: str = "edge"
    emotion_strength: int = 7
    fallback_gtts: bool = True
    default_voice_1: str = "pt-BR-AntonioNeural"
    default_voice_2: str = "pt-BR-FranciscaNeural"
    default_voice_3: str = "pt-BR-AntonioNeural"
    azure_key: str = ""
    azure_region: str = ""
    azure_enabled: bool = False

    audio_output: str = "browser"
    browser_audio_fallback: bool = True

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
        self.twitch_access_token = str(self.twitch_access_token).strip()
        self.twitch_refresh_token = str(self.twitch_refresh_token).strip()
        self.twitch_user_id = str(self.twitch_user_id).strip()
        self.twitch_login = str(self.twitch_login).strip().lower()
        self.twitch_token_client_id = str(self.twitch_token_client_id).strip()
        self.twitch_scopes = sorted({str(x).strip() for x in (self.twitch_scopes or []) if str(x).strip()})
        self.twitch_channel = str(self.twitch_channel).strip().lstrip("#").lower()
        self.twitch_token = str(self.twitch_token).strip()

        self.active_players = max(1, min(int(self.active_players), 3))
        self.activity_seconds = max(30, min(int(self.activity_seconds), 86_400))
        self.max_pool_users = max(10, min(int(self.max_pool_users), 50_000))
        self.tts_provider = str(self.tts_provider).strip().lower()
        if self.tts_provider not in TTS_PROVIDERS:
            self.tts_provider = "edge"
        self.emotion_strength = max(0, min(int(self.emotion_strength), 10))
        self.audio_output = str(self.audio_output).strip().lower()
        if self.audio_output not in AUDIO_OUTPUTS:
            self.audio_output = "browser"

        self.azure_key = str(self.azure_key).strip()
        self.azure_region = str(self.azure_region).strip()
        self.obs_host = str(self.obs_host).strip() or "127.0.0.1"
        self.web_host = str(self.web_host).strip() or "127.0.0.1"
        self.obs_port = max(1, min(int(self.obs_port), 65_535))
        self.web_port = max(1, min(int(self.web_port), 65_535))

        commands = [self.command_player_1.strip(), self.command_player_2.strip(), self.command_player_3.strip()]
        defaults = ["!jogador1", "!jogador2", "!jogador3"]
        self.command_player_1, self.command_player_2, self.command_player_3 = [c or defaults[i] for i, c in enumerate(commands)]

        for player in (1, 2, 3):
            image_key = f"character_image_{player}"
            image_name = str(getattr(self, image_key, "")).strip()
            setattr(self, image_key, Path(image_name).name if image_name else "")
            for suffix, low, high in (("size", 80, 800), ("intensity", 0, 10), ("x", -1000, 1000), ("y", -1000, 1000)):
                key = f"character_{suffix}_{player}"
                setattr(self, key, max(low, min(int(getattr(self, key)), high)))
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
        if data and "active_players" not in data:
            values["active_players"] = 3
        migrated_to_edge = "tts_provider" not in data and not (data.get("azure_enabled") and data.get("azure_key"))
        if "tts_provider" not in data:
            values["tts_provider"] = "azure" if data.get("azure_enabled") and data.get("azure_key") else "edge"
        if migrated_to_edge:
            for player, fallback in ((1, "pt-BR-AntonioNeural"), (2, "pt-BR-FranciscaNeural"), (3, "pt-BR-AntonioNeural")):
                key = f"default_voice_{player}"
                if str(values.get(key, fallback)) not in EDGE_PT_BR_VOICES:
                    values[key] = fallback
        if (
            "twitch_manual_mode" not in data
            and data.get("twitch_channel")
            and data.get("twitch_token")
            and not data.get("twitch_access_token")
        ):
            values["twitch_manual_mode"] = True
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
    if player not in (1, 2, 3) or not CHARACTER_DIR.exists():
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
