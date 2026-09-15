from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import random
import threading
from typing import Callable

from .config import AppConfig
from .tts import detect_message_style


@dataclass
class PlayerState:
    number: int
    user: str = ""
    message: str = ""
    tts_enabled: bool = True
    voice: str = ""
    style: str = "default"
    effective_style: str = "default"
    speaking: bool = False

    def public(self) -> dict:
        return asdict(self)


class PlayerManager:
    def __init__(self, config: AppConfig):
        self.config = config
        self._lock = threading.RLock()
        self.players = {
            1: PlayerState(1, voice=config.default_voice_1),
            2: PlayerState(2, voice=config.default_voice_2),
            3: PlayerState(3, voice=config.default_voice_3),
        }
        self.pools = {1: OrderedDict(), 2: OrderedDict(), 3: OrderedDict()}
        self.on_selected_message: Callable[[int, str], None] | None = None
        self.on_change: Callable[[], None] | None = None

    def _changed(self) -> None:
        if self.on_change:
            self.on_change()

    def is_active(self, player: int) -> bool:
        return player in self.players and player <= self.config.active_players

    def commands(self) -> dict[int, str]:
        commands = {
            1: self.config.command_player_1.lower(),
            2: self.config.command_player_2.lower(),
            3: self.config.command_player_3.lower(),
        }
        return {n: command for n, command in commands.items() if self.is_active(n)}

    def add_to_pool(self, player: int, username: str, timestamp: datetime | None = None) -> None:
        username = username.strip().lower()
        if not username or not self.is_active(player):
            return
        now = timestamp or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        with self._lock:
            pool = self.pools[player]
            pool.pop(username, None)
            pool[username] = now
            self._prune_pool_locked(player, now)
        self._changed()

    def _prune_pool_locked(self, player: int, now: datetime) -> None:
        pool = self.pools[player]
        threshold = now - timedelta(seconds=self.config.activity_seconds)
        for name in [name for name, seen in pool.items() if seen < threshold]:
            pool.pop(name, None)
        while len(pool) > self.config.max_pool_users:
            pool.popitem(last=False)

    def handle_chat_message(self, username: str, content: str, timestamp: datetime | None = None) -> list[int]:
        username_lower = username.strip().lower()
        content_stripped = content.strip()
        content_lower = content_stripped.lower()

        for player, command in self.commands().items():
            if content_lower in {command, f"!player{player}", f"!jogador{player}"}:
                self.add_to_pool(player, username_lower, timestamp)

        spoken_for: list[int] = []
        changed = False
        with self._lock:
            for number, state in self.players.items():
                if not self.is_active(number):
                    continue
                if state.user and state.user.lower() == username_lower:
                    state.message = content_stripped
                    state.effective_style = detect_message_style(content_stripped, state.style)
                    changed = True
                    if state.tts_enabled:
                        spoken_for.append(number)
        if changed:
            self._changed()
        if self.on_selected_message:
            for number in spoken_for:
                self.on_selected_message(number, content_stripped)
        return spoken_for

    def choose(self, player: int, username: str) -> bool:
        if not self.is_active(player):
            return False
        username = username.strip().lstrip("@").lower()
        if not username:
            return False
        with self._lock:
            state = self.players[player]
            state.user = username
            state.message = f"{username} foi escolhido!"
            state.speaking = False
        self._changed()
        return True

    def pick_random(self, player: int) -> str | None:
        if not self.is_active(player):
            return None
        with self._lock:
            self._prune_pool_locked(player, datetime.now(timezone.utc))
            candidates = list(self.pools[player].keys())
            if not candidates:
                return None
            username = random.choice(candidates)
            self.players[player].user = username
            self.players[player].message = f"{username} foi escolhido!"
            self.players[player].speaking = False
        self._changed()
        return username

    def set_tts(self, player: int, enabled: bool) -> bool:
        if not self.is_active(player):
            return False
        with self._lock:
            self.players[player].tts_enabled = bool(enabled)
        self._changed()
        return True

    def set_voice(self, player: int, voice: str) -> bool:
        if not self.is_active(player) or not voice.strip():
            return False
        with self._lock:
            self.players[player].voice = voice.strip()
        self._changed()
        return True

    def set_style(self, player: int, style: str) -> bool:
        allowed = {"default", "calm", "cheerful", "excited", "sad", "angry", "hopeful", "shouting", "terrified", "whispering", "random"}
        style = style.strip().lower()
        if not self.is_active(player) or style not in allowed:
            return False
        with self._lock:
            self.players[player].style = style
            self.players[player].effective_style = style
        self._changed()
        return True

    def set_speaking(self, player: int, speaking: bool) -> bool:
        if not self.is_active(player):
            return False
        speaking = bool(speaking)
        with self._lock:
            if self.players[player].speaking == speaking:
                return True
            self.players[player].speaking = speaking
        self._changed()
        return True

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active_players": self.config.active_players,
                "players": {str(n): state.public() for n, state in self.players.items()},
                "pool_sizes": {str(n): len(pool) for n, pool in self.pools.items()},
                "commands": {str(n): command for n, command in self.commands().items()},
            }
