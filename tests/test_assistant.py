import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

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

    def test_negated_clear_notes_request_preserves_notes(self):
        self.assistant.respond("remember buy milk")
        self.assertEqual(
            self.assistant.respond("don't forget my notes"), FALLBACK_RESPONSE
        )
        self.assertIn("buy milk", self.assistant.respond("list my notes"))

    def test_name_memory(self):
        self.assistant.respond("my name is Charles")
        self.assertEqual(self.assistant.respond("what is my name?"), "You are Charles.")
        self.assertIn("Charles", self.assistant.respond("hello"))


    def test_psychiatrist_reflects_feeling(self):
        reply = self.assistant.respond("I feel anxious about work")
        self.assertIn("anxious about work", reply)
        self.assertIn("worry", reply)
        self.assertIn("not a therapist", reply)

    def test_psychiatrist_logs_mood_history(self):
        self.assistant.respond("I feel lonely")
        self.assistant.respond("I am exhausted today")
        reply = self.assistant.respond("how have I been feeling")
        self.assertIn("lonely", reply)
        self.assertIn("exhausted", reply)
        self.assertIn("cleared", self.assistant.respond("clear my mood history"))
        self.assertIn("not shared", self.assistant.respond("mood history"))

    def test_psychiatrist_mood_history_is_not_persisted(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            assistant = Assistant(memory=Memory(path), now=lambda: FIXED_NOW)
            assistant.respond("I feel anxious about work")
            self.assertFalse(path.exists())

    def test_crisis_support_mentions_emergency_help(self):
        reply = self.assistant.respond("I feel like I want to die")
        self.assertIn("988", reply)
        self.assertIn("emergency", reply)

    def test_crisis_support_handles_direct_self_harm_phrases(self):
        for message in (
            "I want to harm myself",
            "I want to hurt myself",
            "I cut myself",
            "I am thinking about ending my life",
            "I don't want to live",
        ):
            with self.subTest(message=message):
                self.assertIn("988", self.assistant.respond(message))

    def test_emotional_support_offers_comfort_and_a_tip(self):
        self.assistant.respond("my name is Charles")
        reply = self.assistant.respond("I need some emotional support")
        self.assertIn("Charles", reply)
        self.assertIn("four counts", reply)
        second = self.assistant.respond("I am having a really hard day")
        self.assertNotEqual(reply, second)

    def test_love_support_handles_heartbreak_and_conflict(self):
        reply = self.assistant.respond("we broke up last week and I am heartbroken")
        self.assertIn("grief", reply)
        self.assertIn("respect", reply)
        conflict = self.assistant.respond("my girlfriend and I keep fighting")
        self.assertIn("Conflict", conflict)

    def test_love_support_handles_crush(self):
        reply = self.assistant.respond("I have a crush on someone at work")
        self.assertIn("rejection", reply)

    def test_crisis_support_still_wins_over_support_skills(self):
        reply = self.assistant.respond(
            "my girlfriend left me and I want to die"
        )
        self.assertIn("988", reply)

    def test_help_lists_skills(self):
        reply = self.assistant.respond("help")
        self.assertIn("calculator", reply)

    def test_help_triggers_on_new_patterns(self):
        self.assertIn("calculator", self.assistant.respond("what are your skills"))
        self.assertIn("calculator", self.assistant.respond("list your skills"))

    def test_story_skill_rotates(self):
        first = self.assistant.respond("tell me a story")
        second = self.assistant.respond("tell me another story")
        self.assertIn("Once upon a time", first)
        self.assertNotEqual(first, second)

    def test_joke_skill(self):
        self.assertIn("cache", self.assistant.respond("tell me a joke"))
        self.assertIn("computer", self.assistant.respond("make me laugh"))

    def test_uplift_skill(self):
        self.assertIn("perfect record", self.assistant.respond("cheer me up"))
        self.assertIn("nudge", self.assistant.respond("I need some motivation"))

    def test_console_skill_uses_name(self):
        self.assistant.respond("my name is Charles")
        reply = self.assistant.respond("I am having a rough day")
        self.assertIn("Charles", reply)
        self.assertIn("sorry", reply.lower())

    def test_mental_health_skill_suggests_coping_step(self):
        reply = self.assistant.respond("I feel anxious")
        self.assertIn("breathing", reply.lower())
        self.assertIn("therapist", reply)

    def test_crisis_support_takes_priority(self):
        for message in (
            "hi, I want to kill myself",
            "I have been thinking about hurting myself",
            "I don't want to live anymore",
        ):
            with self.subTest(message=message):
                self.assertIn("988", self.assistant.respond(message))

    def test_emotional_skills_do_not_shadow_others(self):
        self.assertEqual(self.assistant.respond("calculate 21 * 2"), "21 * 2 = 42")
        self.assertIn("Jarvis", self.assistant.respond("hello"))

    def test_registries_keep_independent_rotation(self):
        other = make_assistant()
        self.assertEqual(
            self.assistant.respond("tell me a joke"), other.respond("tell me a joke")
        )

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
