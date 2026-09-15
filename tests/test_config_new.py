import unittest

from chatdeus.config import AppConfig


class NewConfigTests(unittest.TestCase):
    def test_twitch_identity_normalizes(self):
        cfg = AppConfig(
            twitch_login=" SindromeGames ",
            twitch_channel=" #SindromeGames ",
            twitch_scopes=["user:read:chat", "user:read:chat"],
        )
        cfg.normalized()
        self.assertEqual(cfg.twitch_login, "sindromegames")
        self.assertEqual(cfg.twitch_channel, "sindromegames")
        self.assertEqual(cfg.twitch_scopes, ["user:read:chat"])

    def test_v11_channel_token_enable_manual_mode(self):
        cfg = AppConfig.from_dict({"twitch_channel": "Canal", "twitch_token": "oauth-token"})
        self.assertTrue(cfg.twitch_manual_mode)

    def test_managed_login_does_not_enable_legacy_mode(self):
        cfg = AppConfig.from_dict(
            {
                "twitch_channel": "sindromegames",
                "twitch_token": "token-antigo",
                "twitch_access_token": "token-gerenciado",
            }
        )
        self.assertFalse(cfg.twitch_manual_mode)


if __name__ == "__main__":
    unittest.main()
