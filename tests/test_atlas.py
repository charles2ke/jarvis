import unittest

from jarvis import atlas
from jarvis.assistant import FALLBACK_RESPONSE, Assistant
from jarvis.memory import Memory


def make_assistant() -> Assistant:
    return Assistant(memory=Memory(None))


class AtlasDataTests(unittest.TestCase):
    def test_find_country_by_name_and_alias(self):
        self.assertEqual(atlas.find_country("Japan").capital, "Tokyo")
        self.assertEqual(atlas.find_country("  USA ").name, "United States")
        self.assertEqual(atlas.find_country("the netherlands").name, "Netherlands")
        self.assertIsNone(atlas.find_country("Narnia"))
        self.assertIsNone(atlas.find_country(""))

    def test_find_by_capital(self):
        self.assertEqual(atlas.find_by_capital("Paris").name, "France")
        self.assertEqual(atlas.find_by_capital("washington").name, "United States")
        self.assertIsNone(atlas.find_by_capital("Atlantis"))

    def test_countries_in_continent_is_sorted(self):
        names = [country.name for country in atlas.countries_in("oceania")]
        self.assertEqual(names, sorted(names))
        self.assertIn("New Zealand", names)
        self.assertEqual(atlas.countries_in("Atlantis"), [])

    def test_population_formatting(self):
        self.assertIn("billion", atlas.format_population(atlas.find_country("India")))
        self.assertIn("million", atlas.format_population(atlas.find_country("Kenya")))

    def test_every_capital_resolves_to_its_country(self):
        for country in atlas.COUNTRIES:
            with self.subTest(country=country.name):
                self.assertEqual(atlas.find_by_capital(country.capital), country)
                self.assertIn(country.continent, atlas.CONTINENTS)


class AtlasSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = make_assistant()

    def test_capital_lookup(self):
        self.assertEqual(
            self.assistant.respond("what is the capital of Japan?"),
            "The capital of Japan is Tokyo.",
        )
        self.assertEqual(
            self.assistant.respond("what is France's capital?"),
            "The capital of France is Paris.",
        )
        self.assertEqual(
            self.assistant.respond("capital of the united states"),
            "The capital of the United States is Washington, D.C.",
        )

    def test_country_from_capital(self):
        self.assertEqual(
            self.assistant.respond("which country's capital is Paris?"),
            "Paris is the capital of France, in Europe.",
        )
        self.assertIn(
            "Kenya",
            self.assistant.respond("Nairobi is the capital of which country?"),
        )

    def test_continent_currency_and_population(self):
        self.assertEqual(
            self.assistant.respond("what continent is Peru in?"),
            "Peru is in South America.",
        )
        self.assertEqual(
            self.assistant.respond("what is the currency of Japan?"),
            "Japan uses the Japanese yen.",
        )
        self.assertIn("billion", self.assistant.respond("population of India"))

    def test_countries_in_continent(self):
        reply = self.assistant.respond("what countries are in Oceania?")
        self.assertIn("Australia", reply)
        self.assertIn("New Zealand", reply)
        self.assertIn("Chile", self.assistant.respond("list countries in South America"))

    def test_country_profile(self):
        reply = self.assistant.respond("tell me about the country Ghana")
        self.assertIn("Africa", reply)
        self.assertIn("Accra", reply)
        self.assertIn("Ghanaian cedi", reply)

    def test_unknown_place_is_reported(self):
        reply = self.assistant.respond("what is the capital of Narnia?")
        self.assertIn("Narnia", reply)
        self.assertIn("atlas", reply)

    def test_capital_is_not_treated_as_country(self):
        reply = self.assistant.respond("population of London")
        self.assertIn("London", reply)
        self.assertIn("atlas", reply)

    def test_atlas_does_not_shadow_other_skills(self):
        self.assertEqual(self.assistant.respond("calculate 21 * 2"), "21 * 2 = 42")
        self.assertIn("Jarvis", self.assistant.respond("hello"))
        self.assertEqual(
            self.assistant.respond("tell me about my weekend plans"), FALLBACK_RESPONSE
        )

    def test_atlas_listed_in_help(self):
        self.assertIn("atlas", self.assistant.respond("help"))


if __name__ == "__main__":
    unittest.main()
