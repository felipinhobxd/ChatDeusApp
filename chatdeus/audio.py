from __future__ import annotations

import logging
from pathlib import Path
import queue
import threading
import time
from typing import Callable

from .state import PlayerManager
from .tts import TTSManager

log = logging.getLogger(__name__)


class AudioWorker:
    """Fila única para evitar falas simultâneas e manter a ordem do chat."""

    def __init__(self, tts: TTSManager, state: PlayerManager, before_play: Callable[[int], None] | None = None, after_play: Callable[[int], None] | None = None):
        self.tts = tts
        self.state = state
        self.before_play = before_play
        self.after_play = after_play
        self._queue: queue.Queue[tuple[int, str] | None] = queue.Queue(maxsize=100)
        self._thread = threading.Thread(target=self._run, name="chatdeus-audio", daemon=True)
        self._started = False

    def start(self) -> None:
        if not self._started:
            self._started = True
            self._thread.start()

    def enqueue(self, player: int, text: str) -> bool:
        if not text.strip():
            return False
        self.start()
        try:
            self._queue.put_nowait((player, text))
            return True
        except queue.Full:
            log.warning("Fila de TTS cheia; mensagem descartada.")
            return False

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            player, text = item
            try:
                current = self.state.players[player]
                audio_path = self.tts.synthesize(text, current.voice, current.style)
                if not audio_path:
                    continue
                if self.before_play:
                    self.before_play(player)
                self._play(audio_path)
            except Exception:
                log.exception("Erro reproduzindo TTS.")
            finally:
                if self.after_play:
                    try:
                        self.after_play(player)
                    except Exception:
                        log.exception("Erro ao finalizar integração com OBS.")
                self._queue.task_done()

    @staticmethod
    def _play(path: Path) -> None:
        import pygame
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
        finally:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            except Exception:
                pass
            try:
                path.unlink(missing_ok=True)
            except OSError:
                log.debug("Não foi possível apagar arquivo temporário %s", path)
