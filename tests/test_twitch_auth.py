import unittest
from unittest.mock import patch

from chatdeus.config import AppConfig
from chatdeus.twitch_auth import TwitchAuthManager, TWITCH_CLIENT_ID


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class TwitchAuthTests(unittest.TestCase):
    def setUp(self):
        self.saved = []
        self.config = AppConfig(twitch_access_token="token-antigo", twitch_refresh_token="refresh-antigo")
        self.manager = TwitchAuthManager(self.config, save_func=lambda cfg: self.saved.append(cfg.to_dict()))

    @patch("chatdeus.twitch_auth.requests.get")
    def test_validate_sets_account_and_channel(self, get):
        get.return_value = FakeResponse(
            200,
            {
                "client_id": TWITCH_CLIENT_ID,
                "login": "SindromeGames",
                "user_id": "123",
                "scopes": ["user:read:chat"],
                "expires_in": 12000,
            },
        )
        session = self.manager.ensure_valid()
        self.assertEqual(session.login, "sindromegames")
        self.assertEqual(self.config.twitch_channel, "sindromegames")
        self.assertFalse(self.config.twitch_manual_mode)
        self.assertTrue(self.saved)

    @patch("chatdeus.twitch_auth.requests.post")
    @patch("chatdeus.twitch_auth.requests.get")
    def test_refresh_public_client_rotates_refresh_token_without_secret(self, get, post):
        get.side_effect = [
            FakeResponse(401, {"message": "invalid access token"}),
            FakeResponse(
                200,
                {
                    "client_id": TWITCH_CLIENT_ID,
                    "login": "sindromegames",
                    "user_id": "123",
                    "scopes": ["user:read:chat"],
                    "expires_in": 14000,
                },
            ),
        ]
        post.return_value = FakeResponse(
            200,
            {
                "access_token": "token-novo",
                "refresh_token": "refresh-novo",
                "scope": ["user:read:chat"],
            },
        )
        session = self.manager.ensure_valid()
        self.assertTrue(session.refreshed)
        self.assertEqual(self.config.twitch_access_token, "token-novo")
        self.assertEqual(self.config.twitch_refresh_token, "refresh-novo")
        sent = post.call_args.kwargs["data"]
        self.assertEqual(sent["client_id"], TWITCH_CLIENT_ID)
        self.assertNotIn("client_secret", sent)

    @patch("chatdeus.twitch_auth.webbrowser.open")
    @patch("chatdeus.twitch_auth.requests.get")
    @patch("chatdeus.twitch_auth.requests.post")
    def test_device_flow_stores_tokens_and_account(self, post, get, open_browser):
        self.config.twitch_access_token = ""
        self.config.twitch_refresh_token = ""
        post.side_effect = [
            FakeResponse(
                200,
                {
                    "device_code": "device-1",
                    "expires_in": 1800,
                    "interval": 1,
                    "user_code": "ABCDEFGH",
                    "verification_uri": "https://www.twitch.tv/activate?device-code=ABCDEFGH",
                },
            ),
            FakeResponse(
                200,
                {
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "scope": ["user:read:chat"],
                },
            ),
        ]
        get.return_value = FakeResponse(
            200,
            {
                "client_id": TWITCH_CLIENT_ID,
                "login": "sindromegames",
                "user_id": "123",
                "scopes": ["user:read:chat"],
                "expires_in": 14000,
            },
        )
        self.manager._pending = True
        self.manager._device_login_worker()
        self.assertEqual(self.config.twitch_login, "sindromegames")
        self.assertEqual(self.config.twitch_refresh_token, "refresh-1")
        open_browser.assert_called_once()


if __name__ == "__main__":
    unittest.main()
