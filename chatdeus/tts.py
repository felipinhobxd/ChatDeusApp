from __future__ import annotations

import asyncio
import html
import logging
from pathlib import Path
import random
import tempfile
import uuid

from .config import AppConfig, EDGE_PT_BR_VOICES

log = logging.getLogger(__name__)

PT_BR_VOICES = [
    ("pt-BR-AntonioNeural", "Antônio"),
    ("pt-BR-FranciscaNeural", "Francisca"),
    ("pt-BR-ThalitaNeural", "Thalita (Azure)"),
    ("pt-BR-BrendaNeural", "Brenda (Azure)"),
    ("pt-BR-DonatoNeural", "Donato (Azure)"),
    ("pt-BR-ElzaNeural", "Elza (Azure)"),
    ("pt-BR-FabioNeural", "Fábio (Azure)"),
    ("pt-BR-GiovannaNeural", "Giovanna (Azure)"),
    ("pt-BR-HumbertoNeural", "Humberto (Azure)"),
    ("pt-BR-JulioNeural", "Júlio (Azure)"),
    ("pt-BR-LeilaNeural", "Leila (Azure)"),
    ("pt-BR-ManuelaNeural", "Manuela (Azure)"),
    ("pt-BR-NicolauNeural", "Nicolau (Azure)"),
    ("pt-BR-ValerioNeural", "Valério (Azure)"),
    ("pt-BR-YaraNeural", "Yara (Azure)"),
]
VOICE_STYLES = [
    ("default", "Padrão"), ("calm", "Calmo"), ("random", "Aleatório"),
    ("cheerful", "Alegre"), ("excited", "Animado"), ("sad", "Triste"),
    ("angry", "Bravo"), ("hopeful", "Esperançoso"), ("shouting", "Gritando"),
    ("terrified", "Assustado"), ("whispering", "Sussurrando"),
]
PREFIX_STYLES = {
    "(bravo)": "angry", "(angry)": "angry", "(alegre)": "cheerful", "(cheerful)": "cheerful",
    "(animado)": "excited", "(excited)": "excited", "(esperançoso)": "hopeful", "(esperancoso)": "hopeful",
    "(hopeful)": "hopeful", "(triste)": "sad", "(sad)": "sad", "(gritando)": "shouting",
    "(grito)": "shouting", "(shouting)": "shouting", "(assustado)": "terrified", "(terrified)": "terrified",
    "(sussurro)": "whispering", "(sussurrando)": "whispering", "(whisper)": "whispering",
    "(whispering)": "whispering", "(aleatorio)": "random", "(aleatório)": "random", "(random)": "random",
}
RANDOM_STYLES = ["calm", "cheerful", "excited", "sad", "angry", "hopeful", "shouting", "terrified", "whispering"]
EMOTION_PROSODY = {
    "default": (0, 0, 0), "calm": (-15, -8, -5), "cheerful": (12, 20, 5),
    "excited": (24, 34, 8), "sad": (-20, -18, -8), "angry": (14, -8, 15),
    "hopeful": (8, 15, 3), "shouting": (28, 24, 24), "terrified": (28, 42, 8),
    "whispering": (-25, 4, -35),
}


def parse_message_style(text: str, style: str) -> tuple[str, str]:
    stripped = text.strip(); lower = stripped.lower()
    for prefix, prefix_style in PREFIX_STYLES.items():
        if lower.startswith(prefix): return stripped[len(prefix):].lstrip(), prefix_style
    return stripped, style


def detect_message_style(text: str, fallback: str = "default") -> str:
    return parse_message_style(text, fallback)[1]


def emotion_prosody(style: str, strength: int = 7) -> tuple[str, str, str]:
    rate, pitch, volume = EMOTION_PROSODY.get(style, EMOTION_PROSODY["default"])
    scale = max(0, min(int(strength), 10)) / 10.0
    rate, pitch, volume = round(rate * scale), round(pitch * scale), round(volume * scale)
    return f"{rate:+d}%", f"{pitch:+d}Hz", f"{volume:+d}%"


class TTSManager:
    def __init__(self, config: AppConfig): self.config = config
    @property
    def azure_ready(self) -> bool: return bool(self.config.azure_key.strip() and self.config.azure_region.strip())
    @property
    def provider_label(self) -> str:
        return {"edge": "Microsoft Edge TTS grátis", "gtts": "gTTS grátis", "azure": "Azure TTS"}.get(self.config.tts_provider, self.config.tts_provider)

    def synthesize(self, text: str, voice: str, style: str = "default") -> Path | None:
        text, style = parse_message_style(text, style)
        if not text: return None
        if style == "random": style = random.choice(RANDOM_STYLES)
        provider = self.config.tts_provider
        try:
            if provider == "edge": return self._edge(text, voice, style)
            if provider == "azure" and self.azure_ready:
                path = self._azure(text, voice, style)
                if path: return path
            if provider == "gtts": return self._gtts(text, style)
        except Exception:
            log.exception("Falha no provedor TTS %s.", provider)
        if self.config.fallback_gtts and provider != "gtts":
            try: return self._gtts(text, style)
            except Exception: log.exception("Falha no fallback gTTS.")
        return None

    def _temp_path(self, suffix: str) -> Path:
        folder = Path(tempfile.gettempdir()) / "ChatDeusApp"; folder.mkdir(parents=True, exist_ok=True)
        return folder / f"fala-{uuid.uuid4().hex}{suffix}"

    def _edge(self, text: str, voice: str, style: str) -> Path:
        import edge_tts
        if voice not in EDGE_PT_BR_VOICES:
            log.info("Voz %s não está no conjunto Edge pt-BR; usando Francisca.", voice)
            voice = "pt-BR-FranciscaNeural"
        rate, pitch, volume = emotion_prosody(style, self.config.emotion_strength)
        output = self._temp_path(".mp3")
        async def generate() -> None:
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch, volume=volume)
            await communicate.save(str(output))
        asyncio.run(generate())
        if not output.exists() or output.stat().st_size == 0: raise RuntimeError("O Microsoft Edge TTS não gerou áudio.")
        return output

    def _azure(self, text: str, voice: str, style: str) -> Path | None:
        import azure.cognitiveservices.speech as speechsdk
        speech_config = speechsdk.SpeechConfig(subscription=self.config.azure_key, region=self.config.azure_region)
        speech_config.speech_synthesis_voice_name = voice
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
        safe_text = html.escape(text)
        inner = safe_text if style == "default" else f"<mstts:express-as style='{html.escape(style)}'>{safe_text}</mstts:express-as>"
        ssml = "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xmlns:mstts='http://www.w3.org/2001/mstts' xml:lang='pt-BR'>" + f"<voice name='{html.escape(voice)}'>{inner}</voice></speak>"
        result = synthesizer.speak_ssml_async(ssml).get()
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted and style != "default":
            plain = "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='pt-BR'>" + f"<voice name='{html.escape(voice)}'>{safe_text}</voice></speak>"
            result = synthesizer.speak_ssml_async(plain).get()
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted: return None
        output = self._temp_path(".wav"); speechsdk.AudioDataStream(result).save_to_wav_file(str(output)); return output

    def _gtts(self, text: str, style: str = "default") -> Path:
        from gtts import gTTS
        output = self._temp_path(".mp3"); slow = style in {"calm", "sad", "whispering"}
        gTTS(text=text, lang="pt-br", slow=slow).save(str(output)); return output
