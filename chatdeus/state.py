from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
import random
import threading
from typing import Callable

from .config import AppConfig


@dataclass
class PlayerState:
    number: int
    user: str = ""
    message: str = ""
    tts_enabled: bool = True
    voice: str = ""
    style: str = "default"

    def public(self) -> dict:
        return asdict(self)


class PlayerManager:
    """Estado thread-safe dos três jogadores e das filas de espectadores."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._lock = threading.RLock()
        self.players = {
            1: PlayerState(1, voice=config.default_voice_1),
            2: PlayerState(2, voice=config.default_voice_2),
            3: PlayerState(3, voice=config.default_voice_3),
        }
        self.pools: dict[int, OrderedDict[str, datetime]] = {
            1: OrderedDict(),
            2: OrderedDict(),
            3: OrderedDict(),
        }
        self.on_selected_message: Callable[[int, str], None] | None = None

    def commands(self) -> dict[int, str]:
        return {
            1: self.config.command_player_1.lower(),
            2: self.config.command_player_2.lower(),
            3: self.config.command_player_3.lower(),
        }

    def add_to_pool(self, player: int, username: str, timestamp: datetime | None = None) -> None:
        username = username.strip().lower()
        if not username or player not in self.pools:
            return
        now = timestamp or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        with self._lock:
            pool = self.pools[player]
            pool.pop(username, None)
            pool[username] = now
            self._prune_pool_locked(player, now)

    def _prune_pool_locked(self, player: int, now: datetime) -> None:
        pool = self.pools[player]
        threshold = now - timedelta(seconds=self.config.activity_seconds)
        expired = [name for name, seen in pool.items() if seen < threshold]
        for name in expired:
            pool.pop(name, None)
        while len(pool) > self.config.max_pool_users:
            pool.popitem(last=False)

    def handle_chat_message(
        self,
        username: str,
        content: str,
        timestamp: datetime | None = None,
    ) -> list[int]:
        username_lower = username.strip().lower()
        content_stripped = content.strip()
        content_lower = content_stripped.lower()

        for player, command in self.commands().items():
            aliases = {command, f"!player{player}", f"!jogador{player}"}
            if content_lower in aliases:
                self.add_to_pool(player, username_lower, timestamp)

        spoken_for: list[int] = []
        with self._lock:
            for number, state in self.players.items():
                if state.user and state.user.lower() == username_lower:
                    state.message = content_stripped
                    if state.tts_enabled:
                        spoken_for.append(number)

        if self.on_selected_message:
            for number in spoken_for:
                self.on_selected_message(number, content_stripped)
        return spoken_for

    def choose(self, player: int, username: str) -> bool:
        if player not in self.players:
            return False
        username = username.strip().lstrip("@").lower()
        if not username:
            return False
        with self._lock:
            state = self.players[player]
            state.user = username
            state.message = f"{username} foi escolhido!"
        return True

    def pick_random(self, player: int) -> str | None:
        if player not in self.players:
            return None
        with self._lock:
            self._prune_pool_locked(player, datetime.now(timezone.utc))
            candidates = list(self.pools[player].keys())
            if not candidates:
                return None
            username = random.choice(candidates)
            self.players[player].user = username
            self.players[player].message = f"{username} foi escolhido!"
            return username

    def set_tts(self, player: int, enabled: bool) -> bool:
        if player not in self.players:
            return False
        with self._lock:
            self.players[player].tts_enabled = bool(enabled)
        return True

    def set_voice(self, player: int, voice: str) -> bool:
        if player not in self.players or not voice.strip():
            return False
        with self._lock:
            self.players[player].voice = voice.strip()
        return True

    def set_style(self, player: int, style: str) -> bool:
        allowed = {
            "default", "calm", "cheerful", "excited", "sad", "angry",
            "hopeful", "shouting", "terrified", "whispering", "random",
        }
        style = style.strip().lower()
        if player not in self.players or style not in allowed:
            return False
        with self._lock:
            self.players[player].style = style
        return True

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "players": {str(n): state.public() for n, state in self.players.items()},
                "pool_sizes": {str(n): len(pool) for n, pool in self.pools.items()},
                "commands": {str(n): cmd for n, cmd in self.commands().items()},
            }
