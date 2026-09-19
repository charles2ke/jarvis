import unittest

from jarvis import Assistant
from jarvis.units import (
    ConversionError,
    convert,
    describe_conversion,
    describe_units,
    find_unit,
)


class UnitConversionTests(unittest.TestCase):
    def test_length_conversions(self):
        self.assertAlmostEqual(convert(10, "km", "miles"), 6.2137119, places=6)
        self.assertAlmostEqual(convert(12, "inches", "ft"), 1.0, places=9)
        self.assertAlmostEqual(convert(1852, "metres", "nautical mile"), 1.0, places=9)

    def test_mass_and_volume_conversions(self):
        self.assertAlmostEqual(convert(1, "kg", "pounds"), 2.2046226, places=6)
        self.assertAlmostEqual(convert(1, "gallon", "litres"), 3.785411784, places=9)

    def test_temperature_uses_offsets(self):
        self.assertAlmostEqual(convert(100, "celsius", "fahrenheit"), 212.0, places=9)
        self.assertAlmostEqual(convert(-40, "f", "c"), -40.0, places=9)
        self.assertAlmostEqual(convert(0, "c", "kelvin"), 273.15, places=9)
        self.assertAlmostEqual(convert(300, "kelvin", "celsius"), 26.85, places=9)

    def test_speed_and_area_conversions(self):
        self.assertAlmostEqual(convert(1, "knot", "kph"), 1.852, places=9)
        self.assertAlmostEqual(convert(1, "hectare", "square metres"), 10000.0, places=6)

    def test_round_trip(self):
        self.assertAlmostEqual(convert(convert(5, "miles", "km"), "km", "miles"), 5.0)

    def test_rejects_mismatched_families(self):
        with self.assertRaises(ConversionError):
            convert(1, "kg", "metres")

    def test_rejects_unknown_unit(self):
        with self.assertRaises(ConversionError):
            convert(1, "parsecs", "metres")

    def test_degree_prefix_and_plurals(self):
        self.assertEqual(find_unit("degrees Celsius").family, "temperature")
        self.assertEqual(find_unit("Kilometres").name, "kilometre")

    def test_describe_conversion_formats_singular(self):
        self.assertEqual(describe_conversion(1, "km", "m"), "1 kilometre = 1000 metres.")

    def test_describe_units_lists_families(self):
        summary = describe_units()
        for family in ("length", "mass", "volume", "time", "temperature", "speed", "area"):
            self.assertIn(family, summary)


class UnitSkillTests(unittest.TestCase):
    def setUp(self):
        self.assistant = Assistant()

    def test_convert_phrasing(self):
        self.assertIn("miles", self.assistant.respond("convert 10 km to miles"))

    def test_how_many_phrasing(self):
        reply = self.assistant.respond("how many pounds is 70 kg")
        self.assertIn("pounds", reply)

    def test_bare_phrasing(self):
        self.assertIn("degrees Fahrenheit", self.assistant.respond("100 c in f"))

    def test_mismatched_families_reply(self):
        reply = self.assistant.respond("convert 5 kg to metres")
        self.assertIn("cannot convert", reply)

    def test_rejects_overflowing_amount(self):
        reply = self.assistant.respond(f"convert {'9' * 400} metres to kilometres")
        self.assertEqual(reply, "That value is too large for me to convert.")

    def test_unit_list_skill(self):
        reply = self.assistant.respond("what units can you convert?")
        self.assertIn("temperature", reply)

    def test_calculator_still_routes(self):
        self.assertEqual(self.assistant.respond("calculate 21 * 2"), "21 * 2 = 42")


if __name__ == "__main__":
    unittest.main()
