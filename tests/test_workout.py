import unittest
from datetime import datetime, timedelta

from jarvis.workout import CREDIT, SAFETY_NOTE, WEEK, plan

SATURDAY = datetime(2026, 11, 21, 9, 0)
TUESDAY = datetime(2026, 11, 24, 7, 0)


class WorkoutDayTests(unittest.TestCase):
    def test_today_follows_the_weekday(self):
        for offset in range(7):
            now = SATURDAY + timedelta(days=offset)
            with self.subTest(now=now.strftime("%A")):
                reply = plan("what's my workout today?", now)
                title = WEEK[now.weekday()].title
                self.assertTrue(reply.startswith(f"Today's workout — {title}"))

    def test_tomorrow_wraps_from_saturday_to_sunday(self):
        reply = plan("tomorrow's workout", SATURDAY)
        self.assertTrue(reply.startswith("Tomorrow's workout — Sunday: Rest & Recovery"))

    def test_named_days(self):
        for text in ("workout for Friday", "Friday workout", "fri workout"):
            with self.subTest(text=text):
                self.assertTrue(plan(text, SATURDAY).startswith("Friday: Lower Body"))

    def test_a_day_lists_every_exercise_with_rest_and_safety(self):
        reply = plan("Monday workout", SATURDAY)
        self.assertIn("- Bench Press / Push-ups: 3 Sets, 8–12 Reps, 90s Rest.", reply)
        self.assertIn("Difficulty: Moderate.", reply)
        self.assertIn("- Lat Pulldowns / Pull-ups:", reply)
        self.assertNotIn("•", reply)
        self.assertNotIn("heart-rate target", reply)
        self.assertEqual(reply.splitlines()[-2:], [SAFETY_NOTE, CREDIT])
        self.assertIn("3 Rounds, 12–15 Reps, 45s Rest.", plan("Saturday workout", SATURDAY))

    def test_zone_2_target_is_flagged_as_personal(self):
        reply = plan("Wednesday workout", SATURDAY)
        self.assertIn(
            "The 105–120 BPM heart-rate target comes from the original author's personal "
            "plan; targets vary with age and fitness.",
            reply,
        )


class WorkoutKindTests(unittest.TestCase):
    def test_leg_day_lists_both_lower_body_days(self):
        reply = plan("when is leg day?", SATURDAY)
        self.assertIn("\n- Tue: Lower Body & Core", reply)
        self.assertIn("\n- Fri: Lower Body & Posterior Chain", reply)
        self.assertIn("The next one is Tuesday, in 3 days.", reply)
        self.assertTrue(reply.endswith(CREDIT))

    def test_is_it_leg_day(self):
        self.assertTrue(plan("is it leg day?", SATURDAY).startswith("No, today is Saturday"))
        reply = plan("is it leg day?", TUESDAY)
        self.assertTrue(reply.startswith("Yes, today is a lower-body day.\nToday's workout"))
        self.assertIn("Goblet Squats", reply)

    def test_rest_and_recovery_days(self):
        self.assertTrue(plan("is tomorrow a rest day?", SATURDAY).startswith("Yes"))
        reply = plan("is Wednesday a rest day?", SATURDAY)
        self.assertTrue(reply.startswith("No, Wednesday is Active Recovery."))
        self.assertIn("- Sun: Rest & Recovery", reply)
        self.assertTrue(plan("is Wednesday a recovery day?", SATURDAY).startswith("Yes"))

    def test_week_overview(self):
        reply = plan("weekly workout plan", SATURDAY)
        days = [line for line in reply.splitlines() if line.startswith("- ")]
        self.assertEqual(len(days), 7)
        self.assertEqual(days[5], "- Sat: Full Body Conditioning, 35 min (today)")
        self.assertEqual(plan("show the week", SATURDAY), reply)


class WorkoutRoutingTests(unittest.TestCase):
    def test_other_questions_are_left_alone(self):
        for text in (
            "work out what day it is tomorrow",
            "can you work out 3 + 4",
            "what day is it tomorrow?",
            "things will work out on Friday",
            "is the gym open on Sunday?",
            "what's a good workout for abs?",
            "I just finished my workout",
            "what should I eat after my workout?",
        ):
            with self.subTest(text=text):
                self.assertIsNone(plan(text, SATURDAY))

    def test_a_question_after_a_statement_is_answered(self):
        reply = plan("I did leg day yesterday, what's today's workout?", SATURDAY)
        self.assertTrue(reply.startswith("Today's workout — Saturday"))


if __name__ == "__main__":
    unittest.main()
