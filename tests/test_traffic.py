import unittest

from jarvis import traffic
from jarvis.assistant import Assistant
from jarvis.memory import Memory


def make_assistant() -> Assistant:
    return Assistant(memory=Memory(None))


class TrafficDataTests(unittest.TestCase):
    def test_find_sign_by_name_and_alias(self):
        self.assertEqual(traffic.find_sign("stop").name, "Stop")
        self.assertEqual(traffic.find_sign("YIELD").name, "Give way")
        self.assertEqual(traffic.find_sign("do not enter").name, "No entry")
        self.assertEqual(traffic.find_sign("crosswalk").name, "Pedestrian crossing")
        self.assertIsNone(traffic.find_sign(""))
        self.assertIsNone(traffic.find_sign("teleporter"))

    def test_sign_lookup_tolerates_suffixes_and_typos(self):
        self.assertEqual(traffic.find_sign("stop sign").name, "Stop")
        self.assertEqual(traffic.find_sign("speed limit signs").name, "Speed limit")
        self.assertEqual(traffic.find_sign("roundabot").name, "Roundabout")

    def test_every_sign_belongs_to_a_known_category(self):
        names = {category.name for category in traffic.CATEGORIES}
        for sign in traffic.SIGNS:
            with self.subTest(sign=sign.name):
                self.assertIn(sign.category, names)
                self.assertTrue(sign.meaning)

    def test_signs_in_category(self):
        warnings = traffic.signs_in("warning signs")
        self.assertTrue(warnings)
        self.assertEqual([s.name for s in warnings], sorted(s.name for s in warnings))
        self.assertIn("Level crossing", [s.name for s in warnings])
        self.assertEqual(traffic.signs_in("nonsense"), [])

    def test_conventions(self):
        self.assertIn("Vienna", traffic.find_convention("vienna convention"))
        self.assertIn("Uniform Traffic Control Devices", traffic.find_convention("mutcd"))
        self.assertIsNone(traffic.find_convention("nonsense"))

    def test_suggestions(self):
        self.assertTrue(traffic.suggestions("parking"))
        self.assertEqual(traffic.suggestions(""), [])


class TrafficSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = make_assistant()

    def test_single_sign_lookup(self):
        reply = self.assistant.respond("what does a stop sign mean?")
        self.assertIn("octagon", reply)
        self.assertIn("complete halt", reply)

    def test_regional_variation_is_reported(self):
        reply = self.assistant.respond("what does a give way sign mean?")
        self.assertIn("YIELD", reply)

    def test_category_lookup_lists_signs(self):
        reply = self.assistant.respond("explain warning signs")
        self.assertIn("triangle", reply)
        self.assertIn("Level crossing", reply)

    def test_overview_and_listing(self):
        overview = self.assistant.respond("tell me about traffic signs")
        self.assertIn("Vienna Convention", overview)
        listing = self.assistant.respond("list traffic signs")
        self.assertIn("Speed limit", listing)

    def test_traffic_lights(self):
        reply = self.assistant.respond("what do traffic lights mean?")
        self.assertIn("amber", reply)

    def test_unknown_sign_suggests_alternatives(self):
        reply = self.assistant.respond("what does a teleporter sign mean?")
        self.assertIn("teleporter", reply)

    def test_sign_reachable_without_the_word_sign(self):
        reply = self.assistant.respond("what does a zebra crossing mean?")
        self.assertIn("Pedestrian crossing", reply)

    def test_traffic_does_not_shadow_other_skills(self):
        self.assertEqual(self.assistant.respond("calculate 21 * 2"), "21 * 2 = 42")
        self.assertIn("deoxyribonucleic", self.assistant.respond("what does DNA mean?"))

    def test_traffic_listed_in_help(self):
        self.assertIn("traffic-signs", self.assistant.respond("help"))


if __name__ == "__main__":
    unittest.main()
