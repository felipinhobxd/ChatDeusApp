from __future__ import annotations

import logging
import threading

from .config import AppConfig

log = logging.getLogger(__name__)


class OBSManager:
    """Integração opcional; erros nunca encerram o ChatDeusApp."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._ws = None
        self._lock = threading.RLock()
        self._failed = False

    def _connect(self) -> bool:
        if not self.config.obs_enabled or self._failed:
            return False
        with self._lock:
            if self._ws is not None:
                return True
            try:
                from obswebsocket import obsws
                self._ws = obsws(self.config.obs_host, self.config.obs_port, self.config.obs_password, timeout=2)
                self._ws.connect()
                log.info("OBS WebSocket conectado.")
                return True
            except Exception as exc:
                self._ws = None
                self._failed = True
                log.warning("OBS indisponível; integração desativada nesta sessão: %s", exc)
                return False

    def set_player_active(self, player: int, active: bool) -> None:
        if not self._connect():
            return
        filters = {1: self.config.obs_filter_1, 2: self.config.obs_filter_2, 3: self.config.obs_filter_3}
        source = self.config.obs_source.strip()
        filter_name = filters.get(player, "").strip()
        if not source or not filter_name:
            return
        try:
            from obswebsocket import requests
            with self._lock:
                self._ws.call(requests.SetSourceFilterEnabled(sourceName=source, filterName=filter_name, filterEnabled=active))
        except Exception as exc:
            log.warning("Falha ao alterar filtro do OBS: %s", exc)
