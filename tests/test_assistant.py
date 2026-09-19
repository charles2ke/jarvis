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

    def test_couples_counseling_handles_explicit_requests(self):
        reply = self.assistant.respond("we need couples counseling")
        self.assertIn("couples therapist", reply)
        communication = self.assistant.respond(
            "my wife and I need couples help, we keep arguing about the same thing"
        )
        self.assertIn("argue about the argument", communication)

    def test_couples_counseling_prioritizes_safety(self):
        reply = self.assistant.respond(
            "we need couples counseling because my partner is abusive"
        )
        self.assertIn("immediate safety", reply)
        self.assertIn("individual support", reply)
        self.assertNotIn("trained couples therapist", reply)

    def test_couples_counseling_handles_trust_and_drift(self):
        trust = self.assistant.respond("we are looking for marriage therapy after an affair")
        self.assertIn("Broken trust", trust)
        drift = self.assistant.respond(
            "we want to work on our marriage, we feel like roommates"
        )
        self.assertIn("Drifting apart", drift)

    def test_couples_counseling_does_not_shadow_love_support(self):
        self.assertIn("Conflict", self.assistant.respond("my girlfriend and I keep fighting"))
        self.assertEqual(self.assistant.respond("we need help"), FALLBACK_RESPONSE)

    def test_midlife_counseling_reflects_on_purpose_and_career(self):
        reply = self.assistant.respond("I think I am having a midlife crisis")
        self.assertIn("midlife reckoning", reply)
        career = self.assistant.respond(
            "I'm turning 50 and I hate my job after all these years"
        )
        self.assertIn("job title", career)

    def test_midlife_counseling_handles_regret(self):
        reply = self.assistant.respond("is this all there is, I feel like I wasted my best years")
        self.assertIn("Regret", reply)

    def test_career_counselling_handles_job_loss_and_moves(self):
        reply = self.assistant.respond("I was laid off last month")
        self.assertIn("identity", reply)
        self.assertIn("mentor", reply)
        move = self.assistant.respond("I am thinking about changing careers")
        self.assertIn("trade-offs", move)

    def test_career_counselling_handles_job_search_and_pay(self):
        self.assertIn(
            "numbers game", self.assistant.respond("my job search keeps failing")
        )
        self.assertIn(
            "evidence", self.assistant.respond("how do I ask for a raise?")
        )

    def test_career_counselling_handles_natural_language_topics(self):
        self.assertIn("drains", self.assistant.respond("I am burned out at work"))
        self.assertIn("drains", self.assistant.respond("my manager is toxic"))
        self.assertIn(
            "numbers game", self.assistant.respond("I was rejected for a job")
        )
        self.assertIn(
            "evidence", self.assistant.respond("how do I negotiate my salary?")
        )
        self.assertIn("trade-offs", self.assistant.respond("I want to change jobs"))

    def test_career_counselling_addresses_you_by_name(self):
        self.assistant.respond("my name is Charles")
        self.assertIn("Charles", self.assistant.respond("I hate my job"))

    def test_crisis_support_still_wins_over_career_counselling(self):
        reply = self.assistant.respond("I lost my job and I want to die")
        self.assertIn("988", reply)

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

    def test_role_model_skill(self):
        for message in ("be my role model", "I want to be a better person"):
            with self.subTest(message=message):
                self.assertIn("hold the bar high", self.assistant.respond(message))

    def test_coach_skill_echoes_goal(self):
        self.assertIn(
            "'guitar'", self.assistant.respond("I want to get better at guitar")
        )
        self.assertIn("in your corner", self.assistant.respond("coach me"))

    def test_self_care_skill(self):
        for message in ("self care", "how do I take care of myself"):
            with self.subTest(message=message):
                self.assertIn(
                    "Looking after yourself", self.assistant.respond(message)
                )

    def test_new_skills_do_not_shadow_wellbeing_skills(self):
        self.assertIn("988", self.assistant.respond("I want to kill myself"))
        self.assertIn("therapist", self.assistant.respond("I feel anxious"))

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
