import json
import tempfile
import unittest
from pathlib import Path

from chatdeus.config import AppConfig, load_config, save_config


class ConfigTests(unittest.TestCase):
    def test_normalization(self):
        cfg = AppConfig(twitch_channel=" #MeuCanal ", web_port=5000); cfg.normalized()
        self.assertEqual(cfg.twitch_channel, "meucanal"); self.assertEqual(cfg.command_player_1, "!jogador1")

    def test_round_trip_preserves_unknown_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"; path.write_text(json.dumps({"twitch_channel": "Teste", "future_key": 123}), encoding="utf-8")
            cfg = load_config(path); self.assertEqual(cfg.twitch_channel, "teste"); self.assertEqual(cfg.extra["future_key"], 123)
            save_config(cfg, path); data = json.loads(path.read_text(encoding="utf-8")); self.assertEqual(data["future_key"], 123)


if __name__ == "__main__": unittest.main()
