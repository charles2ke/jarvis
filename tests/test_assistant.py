import unittest
from datetime import datetime

from jarvis.assistant import FALLBACK_RESPONSE, Assistant
from jarvis.memory import Memory


FIXED_NOW = datetime(2026, 9, 18, 14, 30)


def make_assistant() -> Assistant:
    return Assistant(memory=Memory(None), now=lambda: FIXED_NOW)


class AssistantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = make_assistant()

    def test_greeting(self):
        self.assertIn("Jarvis", self.assistant.respond("hello"))

    def test_time_and_date(self):
        self.assertEqual(self.assistant.respond("what is the time?"), "It is 14:30.")
        self.assertIn("18 September 2026", self.assistant.respond("what day is it"))

    def test_calculator(self):
        self.assertEqual(self.assistant.respond("calculate 21 * 2"), "21 * 2 = 42")
        self.assertEqual(self.assistant.respond("3 + 4"), "3 + 4 = 7")
        self.assertIn("divide by zero", self.assistant.respond("calculate 1 / 0"))

    def test_notes_round_trip(self):
        self.assertIn("1 note", self.assistant.respond("remember buy milk"))
        self.assertIn("buy milk", self.assistant.respond("list my notes"))
        self.assertIn("cleared", self.assistant.respond("clear my notes"))
        self.assertIn("no notes", self.assistant.respond("show notes"))

    def test_name_memory(self):
        self.assistant.respond("my name is Charles")
        self.assertEqual(self.assistant.respond("what is my name?"), "You are Charles.")
        self.assertIn("Charles", self.assistant.respond("hello"))

    def test_help_lists_skills(self):
        reply = self.assistant.respond("help")
        self.assertIn("calculator", reply)

    def test_unknown_message_falls_back(self):
        self.assertEqual(
            self.assistant.respond("please pilot the suit"), FALLBACK_RESPONSE
        )

    def test_empty_message(self):
        self.assertEqual(self.assistant.respond("   "), "I am listening.")

    def test_history_records_exchanges(self):
        self.assistant.respond("hello")
        self.assertEqual(len(self.assistant.history), 1)


if __name__ == "__main__":
    unittest.main()
