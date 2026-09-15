from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import threading
import time
import uuid

log = logging.getLogger(__name__)


@dataclass
class BrowserAudioItem:
    item_id: str
    player: int
    path: Path
    started: threading.Event
    done: threading.Event
    created_at: float


class BrowserAudioBroker:
    """Entrega um áudio por vez para a Fonte de Navegador do OBS."""

    def __init__(self, on_change=None):
        self.on_change = on_change
        self._lock = threading.RLock()
        self._current: BrowserAudioItem | None = None
        self._last_client_seen = 0.0

    def _changed(self) -> None:
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                log.exception("Falha ao sinalizar mudança do áudio do navegador.")

    def hello(self) -> None:
        with self._lock:
            self._last_client_seen = time.monotonic()

    @property
    def available(self) -> bool:
        with self._lock:
            return (time.monotonic() - self._last_client_seen) <= 12.0

    def public(self) -> dict:
        with self._lock:
            current = self._current
            return {
                "browser_connected": (time.monotonic() - self._last_client_seen) <= 12.0,
                "current": (
                    {"id": current.item_id, "player": current.player, "url": f"/api/audio/file/{current.item_id}"}
                    if current
                    else None
                ),
            }

    def play(self, player: int, path: Path, start_timeout: float = 4.0, finish_timeout: float = 120.0) -> bool:
        if not self.available:
            return False
        item = BrowserAudioItem(
            item_id=uuid.uuid4().hex,
            player=player,
            path=path,
            started=threading.Event(),
            done=threading.Event(),
            created_at=time.monotonic(),
        )
        with self._lock:
            self._current = item
        self._changed()
        if not item.started.wait(timeout=start_timeout):
            log.warning("A Fonte de Navegador do OBS não iniciou o áudio; usando fallback.")
            self._clear(item.item_id)
            return False
        if not item.done.wait(timeout=finish_timeout):
            log.warning("A Fonte de Navegador não confirmou o fim do áudio; liberando fila.")
        self._clear(item.item_id)
        return True

    def file_for(self, item_id: str) -> Path | None:
        with self._lock:
            if self._current and self._current.item_id == item_id and self._current.path.is_file():
                return self._current.path
        return None

    def mark_started(self, item_id: str) -> bool:
        with self._lock:
            item = self._current
            if not item or item.item_id != item_id:
                return False
            self._last_client_seen = time.monotonic()
            item.started.set()
        return True

    def mark_finished(self, item_id: str) -> bool:
        with self._lock:
            item = self._current
            if not item or item.item_id != item_id:
                return False
            self._last_client_seen = time.monotonic()
            item.done.set()
        return True

    def _clear(self, item_id: str) -> None:
        with self._lock:
            if self._current and self._current.item_id == item_id:
                self._current = None
        self._changed()
