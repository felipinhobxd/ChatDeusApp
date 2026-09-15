import unittest

from chatdeus.twitch_service import TwitchService


class TwitchServiceTests(unittest.TestCase):
    def test_extract_eventsub_chat_message(self):
        payload = {
            "metadata": {"subscription_type": "channel.chat.message", "message_id": "meta-1"},
            "payload": {
                "event": {
                    "chatter_user_login": "Viewer32",
                    "message_id": "chat-1",
                    "message": {"text": "!jogador1"},
                }
            },
        }
        self.assertEqual(TwitchService.extract_chat_event(payload), ("Viewer32", "!jogador1", "chat-1"))

    def test_ignores_non_chat_notification(self):
        payload = {"metadata": {"subscription_type": "stream.online"}, "payload": {"event": {}}}
        self.assertIsNone(TwitchService.extract_chat_event(payload))


if __name__ == "__main__":
    unittest.main()
