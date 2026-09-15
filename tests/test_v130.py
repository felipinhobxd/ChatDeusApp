import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from chatdeus.browser_audio import BrowserAudioBroker
from chatdeus.config import AppConfig, load_config
from chatdeus.state import PlayerManager
from chatdeus.tts import emotion_prosody, parse_message_style


class ConfigV130Tests(unittest.TestCase):
    def test_new_install_defaults_to_three_players_and_edge(self):
        cfg = AppConfig().normalized()
        self.assertEqual(cfg.active_players, 3)
        self.assertEqual(cfg.tts_provider, "edge")
        self.assertEqual(cfg.audio_output, "browser")

    def test_old_config_migrates_to_three_players(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "config.json"
            p.write_text(json.dumps({"command_player_1": "!jogador1"}), encoding="utf-8")
            cfg = load_config(p)
            self.assertEqual(cfg.active_players, 3)
            self.assertEqual(cfg.tts_provider, "edge")

    def test_limits(self):
        cfg = AppConfig(active_players=9, emotion_strength=99, audio_output="x").normalized()
        self.assertEqual(cfg.active_players, 3)
        self.assertEqual(cfg.emotion_strength, 10)
        self.assertEqual(cfg.audio_output, "browser")


class StateV130Tests(unittest.TestCase):
    def test_inactive_players_do_not_join_or_speak(self):
        m = PlayerManager(AppConfig(active_players=1))
        m.handle_chat_message("ana", "!jogador2")
        self.assertNotIn("ana", m.pools[2])
        self.assertFalse(m.choose(2, "ana"))
        self.assertEqual(m.snapshot()["active_players"], 1)

    def test_two_players_enables_second(self):
        m = PlayerManager(AppConfig(active_players=2))
        m.handle_chat_message("ana", "!jogador2")
        self.assertIn("ana", m.pools[2])


class EmotionV130Tests(unittest.TestCase):
    def test_prefix_and_prosody(self):
        text, style = parse_message_style("(bravo) sai daqui", "default")
        self.assertEqual(text, "sai daqui")
        self.assertEqual(style, "angry")
        rate, pitch, volume = emotion_prosody("shouting", 10)
        self.assertTrue(rate.startswith("+"))
        self.assertTrue(pitch.startswith("+"))
        self.assertTrue(volume.startswith("+"))


class BrowserAudioBrokerTests(unittest.TestCase):
    def test_browser_handshake_and_finish(self):
        broker = BrowserAudioBroker()
        broker.hello()
        self.assertTrue(broker.available)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "x.mp3"
            path.write_bytes(b"test")
            result = []
            t = threading.Thread(target=lambda: result.append(broker.play(1, path, start_timeout=1, finish_timeout=1)))
            t.start()
            deadline = time.time() + 1
            item = None
            while time.time() < deadline:
                item = broker.public()["current"]
                if item:
                    break
                time.sleep(0.01)
            self.assertIsNotNone(item)
            broker.mark_started(item["id"])
            broker.mark_finished(item["id"])
            t.join(2)
            self.assertEqual(result, [True])


if __name__ == "__main__":
    unittest.main()
