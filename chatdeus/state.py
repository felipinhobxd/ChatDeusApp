from __future__ import annotations
from collections import OrderedDict
from dataclasses import dataclass,asdict
from datetime import datetime,timedelta,timezone
import random,threading
from typing import Callable
from .config import AppConfig
from .tts import detect_message_style

@dataclass
class PlayerState:
    number:int;user:str="";message:str="";tts_enabled:bool=True;voice:str="";style:str="default";effective_style:str="default";speaking:bool=False
    def public(self)->dict:return asdict(self)

class PlayerManager:
    def __init__(self,config:AppConfig):
        self.config=config;self._lock=threading.RLock();self.players={1:PlayerState(1,voice=config.default_voice_1),2:PlayerState(2,voice=config.default_voice_2),3:PlayerState(3,voice=config.default_voice_3)};self.pools={1:OrderedDict(),2:OrderedDict(),3:OrderedDict()};self.on_selected_message:Callable[[int,str],None]|None=None;self.on_change:Callable[[],None]|None=None
    def _changed(self):
        if self.on_change:self.on_change()
    def commands(self):return {1:self.config.command_player_1.lower(),2:self.config.command_player_2.lower(),3:self.config.command_player_3.lower()}
    def add_to_pool(self,player,username,timestamp=None):
        username=username.strip().lower()
        if not username or player not in self.pools:return
        now=timestamp or datetime.now(timezone.utc)
        if now.tzinfo is None:now=now.replace(tzinfo=timezone.utc)
        with self._lock:
            pool=self.pools[player];pool.pop(username,None);pool[username]=now;self._prune_pool_locked(player,now)
        self._changed()
    def _prune_pool_locked(self,player,now):
        pool=self.pools[player];threshold=now-timedelta(seconds=self.config.activity_seconds)
        for name in [name for name,seen in pool.items() if seen<threshold]:pool.pop(name,None)
        while len(pool)>self.config.max_pool_users:pool.popitem(last=False)
    def handle_chat_message(self,username,content,timestamp=None):
        username_lower=username.strip().lower();content_stripped=content.strip();content_lower=content_stripped.lower()
        for player,command in self.commands().items():
            if content_lower in {command,f"!player{player}",f"!jogador{player}"}:self.add_to_pool(player,username_lower,timestamp)
        spoken_for=[];changed=False
        with self._lock:
            for number,state in self.players.items():
                if state.user and state.user.lower()==username_lower:
                    state.message=content_stripped;state.effective_style=detect_message_style(content_stripped,state.style);changed=True
                    if state.tts_enabled:spoken_for.append(number)
        if changed:self._changed()
        if self.on_selected_message:
            for number in spoken_for:self.on_selected_message(number,content_stripped)
        return spoken_for
    def choose(self,player,username):
        if player not in self.players:return False
        username=username.strip().lstrip("@").lower()
        if not username:return False
        with self._lock:self.players[player].user=username;self.players[player].message=f"{username} foi escolhido!";self.players[player].speaking=False
        self._changed();return True
    def pick_random(self,player):
        if player not in self.players:return None
        with self._lock:
            self._prune_pool_locked(player,datetime.now(timezone.utc));candidates=list(self.pools[player].keys())
            if not candidates:return None
            username=random.choice(candidates);self.players[player].user=username;self.players[player].message=f"{username} foi escolhido!";self.players[player].speaking=False
        self._changed();return username
    def set_tts(self,player,enabled):
        if player not in self.players:return False
        with self._lock:self.players[player].tts_enabled=bool(enabled)
        self._changed();return True
    def set_voice(self,player,voice):
        if player not in self.players or not voice.strip():return False
        with self._lock:self.players[player].voice=voice.strip()
        self._changed();return True
    def set_style(self,player,style):
        allowed={"default","calm","cheerful","excited","sad","angry","hopeful","shouting","terrified","whispering","random"};style=style.strip().lower()
        if player not in self.players or style not in allowed:return False
        with self._lock:self.players[player].style=style;self.players[player].effective_style=style
        self._changed();return True
    def set_speaking(self,player,speaking):
        if player not in self.players:return False
        speaking=bool(speaking)
        with self._lock:
            if self.players[player].speaking==speaking:return True
            self.players[player].speaking=speaking
        self._changed();return True
    def snapshot(self):
        with self._lock:return {"players":{str(n):s.public() for n,s in self.players.items()},"pool_sizes":{str(n):len(p) for n,p in self.pools.items()},"commands":{str(n):c for n,c in self.commands().items()}}
