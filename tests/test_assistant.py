import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from jarvis.assistant import FALLBACK_RESPONSE, Assistant
from jarvis.memory import Memory
from jarvis.skills import THANKS_REPLIES


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

    def test_delete_single_note(self):
        self.assistant.respond("remember buy milk")
        self.assistant.respond("remember call mum")
        self.assistant.respond("remember water plants")
        reply = self.assistant.respond("delete note 2")
        self.assertEqual(reply, "Deleted note 2: call mum. You now have 2 note(s).")
        listed = self.assistant.respond("list my notes")
        self.assertIn("1. buy milk", listed)
        self.assertIn("2. water plants", listed)
        self.assertNotIn("call mum", listed)
        self.assertIn("Deleted note 1", self.assistant.respond("Forget my note #1."))

    def test_delete_note_out_of_range_or_empty(self):
        self.assertIn("no notes to delete", self.assistant.respond("delete note 1"))
        self.assistant.respond("remember buy milk")
        self.assertIn("There is no note 5", self.assistant.respond("remove note 5"))
        self.assertIn("There is no note 0", self.assistant.respond("delete note 0"))
        self.assertIn(
            "There is no note 1000000",
            self.assistant.respond("delete note 1000000"),
        )
        self.assertIn("buy milk", self.assistant.respond("list my notes"))

    def test_delete_note_handles_unbounded_numeric_input(self):
        self.assistant.respond("remember buy milk")
        huge_index = "9" * 5000
        reply = self.assistant.respond(f"delete note {huge_index}")
        self.assertTrue(reply.startswith(f"There is no note {huge_index}."))
        self.assertIn("buy milk", self.assistant.respond("list my notes"))

    def test_delete_note_does_not_duplicate_sentence_punctuation(self):
        self.assistant.respond("remember call mum.")
        self.assertEqual(
            self.assistant.respond("delete note 1"),
            "Deleted note 1: call mum. You now have 0 note(s).",
        )
        self.assistant.respond("remember stop!")
        self.assertEqual(
            self.assistant.respond("delete note 1"),
            "Deleted note 1: stop! You now have 0 note(s).",
        )

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

    def test_help_with_topic_filters_the_list(self):
        reply = self.assistant.respond("help braille")
        self.assertIn("braille", reply)
        self.assertNotIn("calculator", reply)

    def test_help_with_unknown_topic_falls_back_to_full_list(self):
        reply = self.assistant.respond("help quantum flux")
        self.assertIn("quantum flux", reply)
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

    def test_gmdss_explains_the_system_and_its_equipment(self):
        overview = self.assistant.respond("what is gmdss")
        self.assertIn("Global Maritime Distress and Safety System", overview)
        self.assertIn("1999", overview)
        self.assertIn("406 MHz", self.assistant.respond("what is an EPIRB?"))
        self.assertIn("channel 70", self.assistant.respond("explain dsc"))
        self.assertIn("A4", self.assistant.respond("gmdss sea areas"))
        self.assertIn("MAYDAY", self.assistant.respond("how do I send a distress alert"))

    def test_gmdss_topics_and_unknown_subject(self):
        topics = self.assistant.respond("gmdss topics")
        self.assertIn("NAVTEX", topics)
        self.assertIn("SART", topics)
        reply = self.assistant.respond("gmdss quantum submarine")
        self.assertIn("do not have a GMDSS entry", reply)

    def test_gmdss_does_not_shadow_crisis_support(self):
        self.assertIn("988", self.assistant.respond("mayday, I want to kill myself"))

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

    def test_role_model_skill_rotates_lines(self):
        replies = [self.assistant.respond("be my role model") for _ in range(2)]
        self.assertNotEqual(replies[0], replies[1])
        self.assertNotIn("reminding you", replies[0])
        for reply in replies:
            self.assertNotIn("next choice", reply)
            self.assertNotIn("Tell me what you decide", reply)

    def test_coach_skill_rotates_prompts(self):
        replies = [self.assistant.respond("coach me") for _ in range(2)]
        self.assertNotEqual(replies[0], replies[1])

    def test_self_care_skill_rotates_ideas(self):
        replies = [self.assistant.respond("self care") for _ in range(2)]
        self.assertNotEqual(replies[0], replies[1])

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


class EverydaySkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = make_assistant()

    def skill_for(self, text):
        resolved = self.assistant._resolve(text)
        return resolved[0].name if resolved else None

    def test_time_and_date_phrasings(self):
        for text in ("what time is it", "what time is it now?", "time", "tell me the time please"):
            with self.subTest(text=text):
                self.assertEqual(self.assistant.respond(text), "It is 14:30.")
        self.assertEqual(self.assistant.respond("what's the date"), "Today is Friday, 18 September 2026.")
        self.assertEqual(self.assistant.respond("what year is it?"), "It is 2026.")
        self.assertIn("week 38 of 2026", self.assistant.respond("what week number is it"))

    def test_world_clock_routes(self):
        self.assertTrue(self.assistant.respond("what time is it in Tokyo?").startswith("In Tokyo it is"))
        self.assertIn("ahead of London", self.assistant.respond("time difference between Tokyo and London"))
        self.assertIn("'Narnia'", self.assistant.respond("what time is it in Narnia?"))

    def test_date_calculator(self):
        self.assertEqual(
            self.assistant.respond("how many days until Christmas?"),
            "There are 98 days (14 weeks) until Christmas (Friday, 25 December 2026).",
        )
        self.assertEqual(
            self.assistant.respond("what day of the week is 1 January 2027?"),
            "1 January 2027 is a Friday.",
        )
        self.assertEqual(
            self.assistant.respond("what's the date in 2 weeks"),
            "2 weeks from today is Friday, 2 October 2026.",
        )
        self.assertIn("364 days", self.assistant.respond("how many days from 1 Jan to 31 Dec"))
        self.assertTrue(self.assistant.respond("how long since 1 January 2000").startswith("It has been"))
        self.assertIn("30 May 2026", self.assistant.respond("what date is 90 days after 1 March 2026"))
        self.assertIn("16 September 2026", self.assistant.respond("what date was 2 days ago"))
        self.assertTrue(self.assistant.respond("is 2028 a leap year?").startswith("Yes"))
        self.assertTrue(
            self.assistant.respond("how old am I if I was born on 5 May 1990").startswith("You were born on")
        )

    def test_date_calculator_leaves_other_questions_alone(self):
        self.assertNotEqual(self.skill_for("how long to boil an egg"), "date-calculator")
        self.assertNotEqual(self.skill_for("how long since I last ate"), "date-calculator")
        self.assertEqual(self.skill_for("how long to travel 100 km at 50 km/h"), "science-solver")
        self.assertEqual(self.skill_for("what is the time?"), "time")

    def test_maths(self):
        self.assertEqual(self.assistant.respond("what is 2 to the power of 10?"), "2 to the power of 10 = 1024")
        self.assertEqual(self.assistant.respond("what's the square root of 144"), "square root of 144 = 12")
        self.assertEqual(self.assistant.respond("calculate 2 + 2."), "2 + 2 = 4")
        self.assertEqual(self.assistant.respond("what is 15% of 80?"), "15% of 80 is 12.")
        self.assertEqual(self.assistant.respond("80 less 15%"), "80 decreased by 15% is 68 (a change of 12).")
        self.assertEqual(self.assistant.respond("what is 20% off $50"), "20% off $50 is $40, a saving of $10.")
        self.assertEqual(self.assistant.respond("what percent is 30 out of 120"), "30 is 25% of 120.")
        self.assertEqual(self.assistant.respond("what is 1 as a percentage of 3?"), "1 is about 33.33% of 3.")
        self.assertEqual(
            self.assistant.respond("express 30 out of 120 as a percentage"), "30 is 25% of 120."
        )

    def test_small_talk(self):
        self.assertIn("How are you?", self.assistant.respond("how are you?"))
        self.assertIn("Glad to hear it", self.assistant.respond("not bad, how about you?"))
        self.assertIn("sorry to hear that", self.assistant.respond("not great"))
        self.assertIn(self.assistant.respond("thank you"), [reply.format(name="") for reply in THANKS_REPLIES])
        self.assertIn("Paris", self.assistant.respond("thanks, what is the capital of France"))
        self.assertIn(f"{len(self.assistant.registry)} skills", self.assistant.respond("who are you?"))
        self.assertEqual(self.assistant.respond("good night"), "Good night. Sleep well.")

    def test_small_talk_does_not_shadow_support_skills(self):
        self.assertEqual(self.skill_for("not great, i want to die"), "crisis-support")
        self.assertEqual(self.skill_for("i am not ok"), "emotional-support")
        self.assertEqual(self.skill_for("i feel great"), "psychiatrist")

    def test_repeat(self):
        self.assertEqual(self.assistant.respond("say that again"), "I have not said anything yet.")
        self.assistant.respond("what is the time?")
        self.assertEqual(self.assistant.respond("pardon?"), "It is 14:30.")

    def test_names(self):
        self.assertIn("Chuck", self.assistant.respond("call me chuck please"))
        self.assertEqual(self.assistant.respond("what is my name?"), "You are Chuck.")
        self.assertIn(", Chuck.", self.assistant.respond("thanks"))
        self.assertIn("call you Ada from now on", self.assistant.respond("change my name to Ada"))
        self.assertIn("forgotten", self.assistant.respond("forget my name"))
        self.assertIn("do not know your name", self.assistant.respond("what is my name?"))
        self.assertIsNone(self.skill_for("call me later"))

    def test_notes(self):
        for note in ("buy milk", "call mum", "buy more milk"):
            self.assistant.respond(f"remember {note}")
        self.assertEqual(
            self.assistant.respond("how many notes do I have?"),
            "You have 3 notes. Say 'list my notes' to read them.",
        )
        self.assertEqual(
            self.assistant.respond("search my notes for milk"),
            "2 notes mention 'milk':\n1. buy milk\n3. buy more milk",
        )
        self.assertEqual(
            self.assistant.respond("change note 2 to call dad"),
            "Updated note 2 from 'call mum' to 'call dad'.",
        )
        self.assertIn("Deleted note 3: buy more milk", self.assistant.respond("delete the last note"))
        self.assertEqual(
            self.assistant.respond("list my notes"), "You have 2 notes:\n1. buy milk\n2. call dad"
        )
        self.assertIn("None of your 2 notes", self.assistant.respond("search my notes for bread"))


if __name__ == "__main__":
    unittest.main()
