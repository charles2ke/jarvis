import unittest

from jarvis import percentages
from jarvis.percentages import PercentError


class PercentageTests(unittest.TestCase):
    def test_percent_of(self):
        self.assertEqual(percentages.percent_of("15", "80"), "15% of 80 is 12.")
        self.assertEqual(percentages.percent_of("20", "45.50", "$"), "20% of $45.50 is $9.10.")

    def test_what_percent_says_when_it_rounds(self):
        self.assertEqual(percentages.what_percent("50", "200"), "50 is 25% of 200.")
        self.assertEqual(percentages.what_percent("1", "3"), "1 is about 33.33% of 3.")

    def test_changes_discounts_and_tips(self):
        self.assertEqual(
            percentages.change_by("80", "15", True), "80 increased by 15% is 92 (a change of 12)."
        )
        self.assertEqual(
            percentages.change_by("19.99", "10", False, "$"),
            "$19.99 decreased by 10% is about $17.99 (a change of about $2).",
        )
        self.assertEqual(percentages.discount("20", "50", "$"), "20% off $50 is $40, a saving of $10.")
        self.assertEqual(
            percentages.tip("18", "45.50", "$"),
            "A tip of 18% on $45.50 is $8.19, making $53.69 in total.",
        )
        self.assertEqual(percentages.percent_change("80", "60"), "From 80 to 60 is a decrease of 25%.")

    def test_impossible_or_huge_inputs_are_explained(self):
        with self.assertRaises(PercentError):
            percentages.what_percent("5", "0")
        with self.assertRaises(PercentError):
            percentages.percent_change("0", "5")
        with self.assertRaises(PercentError):
            percentages.percent_of("5", "1" + "0" * 31)


if __name__ == "__main__":
    unittest.main()
