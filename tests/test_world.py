import unittest

from jarvis import atlas
from jarvis.assistant import Assistant
from jarvis.memory import Memory


def make_assistant() -> Assistant:
    return Assistant(memory=Memory(None))


class WorldDataTests(unittest.TestCase):
    def test_every_country_has_a_time_zone(self):
        for country in atlas.COUNTRIES:
            with self.subTest(country=country.name):
                zone = atlas.timezone_for_country(country)
                self.assertIsNotNone(zone)
                self.assertTrue(zone.zone)
                self.assertRegex(zone.utc_offset, r"^UTC[+-]\d{2}:\d{2}$")

    def test_find_city_by_name_and_alias(self):
        self.assertEqual(atlas.find_city("New York").country, "United States")
        self.assertEqual(atlas.find_city("bombay").name, "Mumbai")
        self.assertIsNone(atlas.find_city("Atlantis"))
        self.assertIsNone(atlas.find_city(""))

    def test_every_city_belongs_to_a_known_country(self):
        for city in atlas.CITIES:
            with self.subTest(city=city.name):
                self.assertIsNotNone(atlas.find_country(city.country))

    def test_cities_in_country(self):
        names = [city.name for city in atlas.cities_in("Japan")]
        self.assertEqual(names, sorted(names))
        self.assertIn("Osaka", names)
        self.assertEqual(atlas.cities_in("Narnia"), [])

    def test_wonder_lists(self):
        for category in atlas.WONDER_CATEGORIES:
            with self.subTest(category=category):
                self.assertEqual(len(atlas.wonders_in(category)), 7)
        self.assertEqual(atlas.wonders_in("imaginary wonders"), [])

    def test_find_wonder(self):
        self.assertEqual(atlas.find_wonder("petra").category, "New Seven Wonders of the World")
        self.assertEqual(atlas.find_wonder("northern lights").name, "Aurora")
        self.assertIsNone(atlas.find_wonder("the moon landing"))

    def test_find_event_by_name_and_alias(self):
        self.assertEqual(atlas.find_event("ww2").year, 1939)
        self.assertEqual(atlas.find_event("moon landing").year, 1969)
        self.assertEqual(atlas.find_event("the berlin wall").name, "Fall of the Berlin Wall")
        self.assertIsNone(atlas.find_event(""))
        self.assertIsNone(atlas.find_event("my birthday party"))

    def test_events_in_year(self):
        names = [event.name for event in atlas.events_in_year(1969)]
        self.assertEqual(
            names,
            [
                "Decolonisation of Africa and Asia",
                "The Cold War",
                "The Apollo 11 Moon landing",
            ],
        )
        self.assertTrue(atlas.events_in_year(1943))
        names = [event.name for event in atlas.events_in_year(1945)]
        self.assertEqual(
            names,
            [
                "The Second World War",
                "Founding of the United Nations",
                "Decolonisation of Africa and Asia",
            ],
        )
        self.assertEqual(atlas.events_in_year(1200), [])

    def test_events_in_year_covers_every_year_of_a_span(self):
        for year in range(1939, 1946):
            with self.subTest(year=year):
                names = [event.name for event in atlas.events_in_year(year)]
                self.assertIn("The Second World War", names)


class WorldSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = make_assistant()

    def test_country_time_zone(self):
        reply = self.assistant.respond("what time zone is Japan in?")
        self.assertIn("UTC+09:00", reply)
        self.assertIn("Asia/Tokyo", reply)

    def test_city_time_zone(self):
        reply = self.assistant.respond("time zone of New York")
        self.assertIn("UTC-05:00", reply)
        self.assertIn("the United States", reply)

    def test_multi_zone_country_is_flagged(self):
        self.assertIn("eleven time zones", self.assistant.respond("time zone of Russia"))

    def test_unknown_time_zone(self):
        reply = self.assistant.respond("what is the time zone of Narnia?")
        self.assertIn("Narnia", reply)

    def test_time_zone_does_not_shadow_the_time_skill(self):
        self.assertIn(":", self.assistant.respond("what is the time?"))

    def test_cities_of_a_country(self):
        reply = self.assistant.respond("what cities are in Japan?")
        self.assertIn("Tokyo", reply)
        self.assertIn("Kyoto", reply)

    def test_wonders_lists(self):
        modern = self.assistant.respond("what are the seven wonders of the world?")
        self.assertIn("Machu Picchu", modern)
        ancient = self.assistant.respond("what are the wonders of the ancient world?")
        self.assertIn("Colossus of Rhodes", ancient)
        natural = self.assistant.respond("what are the natural wonders of the world?")
        self.assertIn("Victoria Falls", natural)

    def test_single_wonder_lookup(self):
        reply = self.assistant.respond("tell me about Machu Picchu")
        self.assertIn("Inca", reply)
        self.assertIn("New Seven Wonders of the World", reply)

    def test_history_by_year(self):
        reply = self.assistant.respond("what happened in 1969?")
        self.assertIn("Apollo 11", reply)

    def test_history_by_bc_year(self):
        self.assertIn(
            "Invention of writing",
            self.assistant.respond("what happened in 3200 BC?"),
        )
        self.assertIn(
            "The Agricultural Revolution",
            self.assistant.respond("what happened in 10000 BCE?"),
        )

    def test_history_by_event(self):
        reply = self.assistant.respond("when did the Berlin Wall fall?")
        self.assertIn("1989", reply)

    def test_history_listing(self):
        reply = self.assistant.respond("list major historical events")
        self.assertLess(
            reply.index("The Industrial Revolution"),
            reply.index("The French Revolution"),
        )
        self.assertLess(
            reply.index("Decolonisation of Africa and Asia"),
            reply.index("The Apollo 11 Moon landing"),
        )

    def test_history_unknown_year(self):
        reply = self.assistant.respond("what happened in 1200?")
        self.assertIn("1200", reply)

    def test_city_lookup_through_encyclopedia_fallback(self):
        reply = self.assistant.respond("tell me about Sydney")
        self.assertIn("Australia", reply)
        self.assertIn("UTC+10:00", reply)

    def test_new_skills_listed_in_help(self):
        reply = self.assistant.respond("help")
        for name in ("time-zone", "wonders", "history", "cities"):
            with self.subTest(skill=name):
                self.assertIn(name, reply)


if __name__ == "__main__":
    unittest.main()
