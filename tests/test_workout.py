import unittest
from datetime import datetime, timedelta

from project_support import ProjectTestCase, fake_project, missing_projects

from jarvis import projects, workout
from jarvis.dates import WEEKDAY_NAMES
from jarvis.workout import CREDIT, SAFETY_NOTE, plan

SATURDAY = datetime(2026, 11, 21, 9, 0)
TUESDAY = datetime(2026, 11, 24, 7, 0)


def _exercise(name, stats, rounds=3, rest=60, notes="Keep good form.", difficulty="Easy"):
    return {
        "id": name.lower().replace(" ", "-"),
        "name": name,
        "stats": stats,
        "notes": notes,
        "difficulty": difficulty,
        "restSeconds": rest,
        "rounds": rounds,
    }


def _day(index, focus, minutes, *exercises):
    name = WEEKDAY_NAMES[index]
    return {
        "id": name[:3].lower(),
        "label": name[:3],
        "title": f"{name}: {focus}",
        "description": f"About {focus.lower()}.",
        "estimatedMinutes": minutes,
        "exercises": list(exercises),
    }


# A made-up plan in the shape bridges/workout.mjs returns.
PROGRAM = {
    "title": "Sample Week",
    "week": [
        _day(0, "Upper Body Push", 45, _exercise("Push-ups", "3 Sets • 10 Reps • 60s Rest"),
             _exercise("Rows", "3 Sets • 12 Reps", rest=45, difficulty="Moderate")),
        _day(1, "Lower Body & Core", 40, _exercise("Squats", "3 Sets • 10 Reps • 90s Rest")),
        _day(2, "Active Recovery", 30, _exercise("Easy Cycling", "30 Mins • 100–115 BPM", rounds=1)),
        _day(3, "Upper Body Pull", 40, _exercise("Pull-ups", "4 Sets • 6 Reps • 90s Rest")),
        _day(4, "Lower Body Strength", 40, _exercise("Lunges", "3 Sets • 8 Reps/leg • 90s Rest")),
        _day(5, "Full Body Circuit", 35, _exercise("Burpees", "3 Rounds • 10 Reps • 45s Rest")),
        _day(6, "Rest & Recovery", 20, _exercise("Walk", "20 Mins", rounds=1)),
    ],
}


class FakePlanTestCase(unittest.TestCase):
    def setUp(self):
        workout.program.cache_clear()
        self.addCleanup(workout.program.cache_clear)
        faked = fake_project("workout", {"program": PROGRAM})
        self.calls = faked.__enter__()
        self.addCleanup(faked.__exit__, None, None, None)


class WorkoutDayTests(FakePlanTestCase):
    def test_today_follows_the_weekday(self):
        for offset in range(7):
            now = SATURDAY + timedelta(days=offset)
            with self.subTest(now=now.strftime("%A")):
                title = PROGRAM["week"][now.weekday()]["title"]
                self.assertTrue(plan("what's my workout today?", now).startswith(f"Today's workout — {title}"))

    def test_tomorrow_wraps_from_saturday_to_sunday(self):
        reply = plan("tomorrow's workout", SATURDAY)
        self.assertTrue(reply.startswith("Tomorrow's workout — Sunday: Rest & Recovery"))

    def test_named_days(self):
        for text in ("workout for Friday", "Friday workout", "fri workout"):
            with self.subTest(text=text):
                self.assertTrue(plan(text, SATURDAY).startswith("Friday: Lower Body Strength (about 40 minutes)"))

    def test_a_day_lists_every_exercise_with_rest_and_safety(self):
        reply = plan("Monday workout", SATURDAY)
        self.assertIn("- Push-ups: 3 Sets, 10 Reps, 60s Rest. Keep good form. Difficulty: Easy.", reply)
        self.assertIn("- Rows: 3 Sets, 12 Reps, 45s Rest. Keep good form. Difficulty: Moderate.", reply)
        self.assertNotIn("•", reply)
        self.assertNotIn("heart-rate target", reply)
        self.assertEqual(reply.splitlines()[-2:], [SAFETY_NOTE, CREDIT])

    def test_heart_rate_target_is_flagged_as_personal(self):
        self.assertIn(
            "The 100–115 BPM heart-rate target comes from the original author's personal "
            "plan; targets vary with age and fitness.",
            plan("Wednesday workout", SATURDAY),
        )

    def test_the_plan_is_read_once(self):
        plan("Monday workout", SATURDAY)
        plan("weekly workout plan", SATURDAY)
        self.assertEqual(self.calls, [("program", None)])


class WorkoutKindTests(FakePlanTestCase):
    def test_leg_day_lists_the_lower_body_days(self):
        reply = plan("when is leg day?", SATURDAY)
        self.assertIn("The plan's lower-body days are Tuesday and Friday:", reply)
        self.assertIn("\n- Tue: Lower Body & Core, 40 min — Squats", reply)
        self.assertIn("\n- Fri: Lower Body Strength, 40 min — Lunges", reply)
        self.assertIn("The next one is Tuesday, in 3 days.", reply)
        self.assertTrue(reply.endswith(CREDIT))

    def test_is_it_leg_day(self):
        self.assertTrue(plan("is it leg day?", SATURDAY).startswith("No, today is Saturday"))
        reply = plan("is it leg day?", TUESDAY)
        self.assertTrue(reply.startswith("Yes, today is a lower-body day.\nToday's workout"))
        self.assertIn("Squats", reply)

    def test_rest_and_recovery_days(self):
        self.assertTrue(plan("is tomorrow a rest day?", SATURDAY).startswith("Yes"))
        reply = plan("is Wednesday a rest day?", SATURDAY)
        self.assertTrue(reply.startswith("No, Wednesday is Active Recovery."))
        self.assertIn("- Sun: Rest & Recovery", reply)
        self.assertTrue(plan("is Wednesday a recovery day?", SATURDAY).startswith("Yes"))

    def test_a_kind_the_plan_lacks(self):
        week = [dict(day, title=day["title"].replace("Lower Body", "Legs")) for day in PROGRAM["week"]]
        workout.program.cache_clear()
        with fake_project("workout", {"program": {"title": "Other", "week": week}}):
            self.assertTrue(plan("when is leg day?", SATURDAY).startswith("workout's plan has no lower-body day"))

    def test_week_overview_uses_the_projects_title(self):
        reply = plan("weekly workout plan", SATURDAY)
        self.assertTrue(reply.startswith("The Sample Week:"))
        days = [line for line in reply.splitlines() if line.startswith("- ")]
        self.assertEqual(len(days), 7)
        self.assertEqual(days[5], "- Sat: Full Body Circuit, 35 min (today)")
        self.assertEqual(plan("show the week", SATURDAY), reply)


class WorkoutRoutingTests(FakePlanTestCase):
    def test_other_questions_are_left_alone_without_the_project(self):
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
        self.assertEqual(self.calls, [])

    def test_a_question_after_a_statement_is_answered(self):
        reply = plan("I did leg day yesterday, what's today's workout?", SATURDAY)
        self.assertTrue(reply.startswith("Today's workout — Saturday"))


class WorkoutProjectProblemTests(unittest.TestCase):
    def setUp(self):
        workout.program.cache_clear()
        self.addCleanup(workout.program.cache_clear)

    def test_missing_project_explains_the_setup(self):
        with missing_projects(), self.assertRaises(projects.ProjectUnavailable) as raised:
            plan("Friday workout", SATURDAY)
        self.assertIn("git submodule update --init projects/workout", str(raised.exception))
        self.assertIn("https://charles2ke.github.io/workout/", str(raised.exception))

    def test_an_unexpected_plan_is_an_error(self):
        broken = (
            {"title": "x", "week": PROGRAM["week"][:6]},
            {"title": "x", "week": [dict(PROGRAM["week"][0], exercises=[])] * 7},
            {"title": "x", "week": [dict(PROGRAM["week"][0], estimatedMinutes="45")] * 7},
            None,
        )
        for data in broken:
            workout.program.cache_clear()
            with self.subTest(data=str(data)[:60]), fake_project("workout", {"program": data}):
                with self.assertRaises(projects.ProjectError):
                    plan("Friday workout", SATURDAY)


class WorkoutProjectTests(ProjectTestCase):
    """Runs the real workout project from projects/workout with Node.js."""

    project = "workout"

    def setUp(self):
        workout.program.cache_clear()

    def test_every_day_of_the_real_plan(self):
        for index, name in enumerate(WEEKDAY_NAMES):
            with self.subTest(day=name):
                reply = plan(f"{name} workout", SATURDAY)
                self.assertTrue(reply.startswith(f"{name}: "))
                self.assertNotIn("•", reply)
                self.assertRegex(reply.splitlines()[2], r"^- .+: .+\. .*Difficulty: \w+\.$")
                self.assertEqual(reply.splitlines()[-2:], [SAFETY_NOTE, CREDIT])

    def test_the_real_week_and_day_kinds(self):
        week = plan("weekly workout plan", SATURDAY).splitlines()
        self.assertRegex(week[0], r"^The .+:$")
        self.assertEqual(len([line for line in week if line.startswith("- ")]), 7)
        # Jarvis finds each kind of day by words in the project's day titles.
        for question in ("when is leg day?", "when is arm day?", "when is my rest day?"):
            with self.subTest(question=question):
                self.assertTrue(plan(question, SATURDAY).startswith("The plan's "))


if __name__ == "__main__":
    unittest.main()
