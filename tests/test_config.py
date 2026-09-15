import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import chatdeus.config as config_module
from chatdeus.config import AppConfig,character_file_path,install_character_image,load_config,save_config
class ConfigTests(unittest.TestCase):
    def test_normalization(self):
        cfg=AppConfig(twitch_channel=" #MeuCanal ",web_port=5000,character_size_1=9999,character_intensity_1=-2);cfg.normalized();self.assertEqual(cfg.twitch_channel,"meucanal");self.assertEqual(cfg.command_player_1,"!jogador1");self.assertEqual(cfg.character_size_1,800);self.assertEqual(cfg.character_intensity_1,0)
    def test_round_trip_preserves_unknown_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"config.json";path.write_text(json.dumps({"twitch_channel":"Teste","future_key":123}),encoding="utf-8");cfg=load_config(path);self.assertEqual(cfg.twitch_channel,"teste");self.assertEqual(cfg.extra["future_key"],123);save_config(cfg,path);data=json.loads(path.read_text(encoding="utf-8"));self.assertEqual(data["future_key"],123)
    def test_character_image_is_copied_to_managed_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/"avatar.png";source.write_bytes(b"fake-png");managed=root/"characters"
            with patch.object(config_module,"CHARACTER_DIR",managed):
                filename=install_character_image(1,source);cfg=AppConfig(character_image_1=filename);self.assertEqual(filename,"jogador1.png");self.assertEqual(character_file_path(cfg,1),managed/filename)
if __name__=="__main__":unittest.main()
