import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from chatdeus.config import AppConfig
from chatdeus.state import PlayerManager
class StateTests(unittest.TestCase):
    def setUp(self):self.manager=PlayerManager(AppConfig(activity_seconds=60,max_pool_users=10))
    def test_portuguese_and_legacy_commands_join_pool(self):
        now=datetime.now(timezone.utc);self.manager.handle_chat_message("Ana","!jogador1",now);self.manager.handle_chat_message("Beto","!player2",now);self.assertIn("ana",self.manager.pools[1]);self.assertIn("beto",self.manager.pools[2])
    def test_selected_user_message_updates_state(self):self.manager.choose(1,"@Ana");self.manager.handle_chat_message("Ana","Olá mundo");self.assertEqual(self.manager.players[1].message,"Olá mundo")
    def test_emotion_prefix_updates_effective_style(self):self.manager.choose(1,"Ana");self.manager.handle_chat_message("Ana","(bravo) sai daqui");self.assertEqual(self.manager.players[1].effective_style,"angry")
    def test_speaking_state_notifies_overlay(self):
        changes=[];self.manager.on_change=lambda:changes.append(True);self.manager.set_speaking(1,True);self.assertTrue(self.manager.players[1].speaking);self.assertTrue(changes)
    def test_expired_users_are_pruned_before_random_pick(self):old=datetime.now(timezone.utc)-timedelta(minutes=10);self.manager.add_to_pool(1,"velho",old);self.assertIsNone(self.manager.pick_random(1))
    def test_random_pick_selects_user(self):
        now=datetime.now(timezone.utc);self.manager.add_to_pool(1,"ana",now)
        with patch("chatdeus.state.random.choice",return_value="ana"):picked=self.manager.pick_random(1)
        self.assertEqual(picked,"ana");self.assertEqual(self.manager.players[1].user,"ana")
if __name__=="__main__":unittest.main()
