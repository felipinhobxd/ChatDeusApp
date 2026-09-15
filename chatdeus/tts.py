from __future__ import annotations

import html
import logging
from pathlib import Path
import random
import tempfile
import uuid

from .config import AppConfig

log = logging.getLogger(__name__)

PT_BR_VOICES = [("pt-BR-AntonioNeural","Antônio"),("pt-BR-FranciscaNeural","Francisca"),("pt-BR-ThalitaNeural","Thalita"),("pt-BR-BrendaNeural","Brenda"),("pt-BR-DonatoNeural","Donato"),("pt-BR-ElzaNeural","Elza"),("pt-BR-FabioNeural","Fábio"),("pt-BR-GiovannaNeural","Giovanna"),("pt-BR-HumbertoNeural","Humberto"),("pt-BR-JulioNeural","Júlio"),("pt-BR-LeilaNeural","Leila"),("pt-BR-ManuelaNeural","Manuela"),("pt-BR-NicolauNeural","Nicolau"),("pt-BR-ValerioNeural","Valério"),("pt-BR-YaraNeural","Yara")]
VOICE_STYLES = [("default","Padrão"),("calm","Calmo"),("random","Aleatório"),("cheerful","Alegre"),("excited","Animado"),("sad","Triste"),("angry","Bravo"),("hopeful","Esperançoso"),("shouting","Gritando"),("terrified","Assustado"),("whispering","Sussurrando")]
PREFIX_STYLES = {"(bravo)":"angry","(angry)":"angry","(alegre)":"cheerful","(cheerful)":"cheerful","(animado)":"excited","(excited)":"excited","(esperançoso)":"hopeful","(esperancoso)":"hopeful","(hopeful)":"hopeful","(triste)":"sad","(sad)":"sad","(gritando)":"shouting","(grito)":"shouting","(shouting)":"shouting","(assustado)":"terrified","(terrified)":"terrified","(sussurro)":"whispering","(sussurrando)":"whispering","(whisper)":"whispering","(whispering)":"whispering","(aleatorio)":"random","(aleatório)":"random","(random)":"random"}
RANDOM_STYLES = ["calm","cheerful","excited","sad","angry","hopeful","shouting","terrified","whispering"]

def parse_message_style(text: str, style: str) -> tuple[str,str]:
    stripped=text.strip(); lower=stripped.lower()
    for prefix,prefix_style in PREFIX_STYLES.items():
        if lower.startswith(prefix): return stripped[len(prefix):].lstrip(),prefix_style
    return stripped,style

def detect_message_style(text: str, fallback: str="default") -> str:
    return parse_message_style(text,fallback)[1]

class TTSManager:
    def __init__(self,config:AppConfig): self.config=config
    @property
    def azure_ready(self)->bool: return bool(self.config.azure_enabled and self.config.azure_key.strip() and self.config.azure_region.strip())
    def synthesize(self,text:str,voice:str,style:str="default")->Path|None:
        text,style=parse_message_style(text,style)
        if not text:return None
        if style=="random": style=random.choice(RANDOM_STYLES)
        if self.azure_ready:
            try:
                path=self._azure(text,voice,style)
                if path:return path
            except Exception: log.exception("Falha no Azure TTS; tentando fallback.")
        if self.config.fallback_gtts:
            try:return self._gtts(text)
            except Exception:log.exception("Falha no fallback gTTS.")
        return None
    def _temp_path(self,suffix:str)->Path:
        folder=Path(tempfile.gettempdir())/"ChatDeusApp";folder.mkdir(parents=True,exist_ok=True);return folder/f"fala-{uuid.uuid4().hex}{suffix}"
    def _azure(self,text:str,voice:str,style:str)->Path|None:
        import azure.cognitiveservices.speech as speechsdk
        speech_config=speechsdk.SpeechConfig(subscription=self.config.azure_key,region=self.config.azure_region);speech_config.speech_synthesis_voice_name=voice
        synthesizer=speechsdk.SpeechSynthesizer(speech_config=speech_config,audio_config=None);safe_text=html.escape(text)
        inner=safe_text if style=="default" else f"<mstts:express-as style='{html.escape(style)}'>{safe_text}</mstts:express-as>"
        ssml="<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xmlns:mstts='http://www.w3.org/2001/mstts' xml:lang='pt-BR'>"+f"<voice name='{html.escape(voice)}'>{inner}</voice></speak>"
        result=synthesizer.speak_ssml_async(ssml).get()
        if result.reason!=speechsdk.ResultReason.SynthesizingAudioCompleted and style!="default":
            plain="<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='pt-BR'>"+f"<voice name='{html.escape(voice)}'>{safe_text}</voice></speak>";result=synthesizer.speak_ssml_async(plain).get()
        if result.reason!=speechsdk.ResultReason.SynthesizingAudioCompleted:return None
        output=self._temp_path(".wav");speechsdk.AudioDataStream(result).save_to_wav_file(str(output));return output
    def _gtts(self,text:str)->Path:
        from gtts import gTTS
        output=self._temp_path(".mp3");gTTS(text=text,lang="pt-br",slow=False).save(str(output));return output
