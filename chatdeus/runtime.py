from __future__ import annotations
import logging
from pathlib import Path
import threading,webbrowser
from .audio import AudioWorker
from .config import AppConfig,character_file_path
from .obs import OBSManager
from .state import PlayerManager
from .tts import TTSManager
from .twitch_service import TwitchService
from .web import create_app
log=logging.getLogger(__name__)

class Runtime:
    def __init__(self,config:AppConfig):
        self.config=config.normalized();self._change_condition=threading.Condition();self._state_version=0;self.state=PlayerManager(self.config);self.state.on_change=self.signal_state_change;self.tts=TTSManager(self.config);self.obs=OBSManager(self.config);self.audio=AudioWorker(self.tts,self.state,before_play=self._before_play,after_play=self._after_play);self.state.on_selected_message=self.audio.enqueue;self.twitch=TwitchService(self.config,self.state);self.flask_app=create_app(self);self.web_thread=None
    @property
    def base_url(self):
        visible_host="127.0.0.1" if self.config.web_host in {"0.0.0.0","::"} else self.config.web_host;return f"http://{visible_host}:{self.config.web_port}"
    def _before_play(self,player):self.state.set_speaking(player,True);self.obs.set_player_active(player,True)
    def _after_play(self,player):self.obs.set_player_active(player,False);self.state.set_speaking(player,False)
    def signal_state_change(self):
        with self._change_condition:self._state_version+=1;self._change_condition.notify_all()
    def wait_for_change(self,after_version,timeout=15.0):
        with self._change_condition:
            if self._state_version<=after_version:self._change_condition.wait(timeout=timeout)
            return self._state_version
    def character_file(self,player)->Path|None:return character_file_path(self.config,player)
    def character_public(self,player):
        path=self.character_file(player);v=path.stat().st_mtime_ns if path else 0
        return {"configured":bool(path),"url":f"/character/{player}?v={v}" if path else "","size":getattr(self.config,f"character_size_{player}"),"intensity":getattr(self.config,f"character_intensity_{player}"),"x":getattr(self.config,f"character_x_{player}"),"y":getattr(self.config,f"character_y_{player}"),"mirror":getattr(self.config,f"character_mirror_{player}"),"idle":getattr(self.config,f"character_idle_{player}"),"speaking":getattr(self.config,f"character_speaking_{player}")}
    def apply_visual_config(self,updated):
        updated.normalized();fields=["command_player_1","command_player_2","command_player_3"]
        for p in (1,2,3):fields.extend([f"character_image_{p}",f"character_size_{p}",f"character_intensity_{p}",f"character_x_{p}",f"character_y_{p}",f"character_mirror_{p}",f"character_idle_{p}",f"character_speaking_{p}"])
        for f in fields:setattr(self.config,f,getattr(updated,f))
        self.state.config=self.config;self.signal_state_change()
    def start(self):
        self.audio.start();self.twitch.start()
        if not self.web_thread or not self.web_thread.is_alive():self.web_thread=threading.Thread(target=self._run_web,name="chatdeus-web",daemon=True);self.web_thread.start()
    def _run_web(self):self.flask_app.run(host=self.config.web_host,port=self.config.web_port,threaded=True,use_reloader=False)
    def open_panel(self):webbrowser.open(self.base_url)
