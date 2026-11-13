import unittest
from datetime import date

from jarvis import dates
from jarvis.dates import DateError, parse_date

TODAY = date(2026, 11, 13)  # a Friday


class ParseDateTests(unittest.TestCase):
    def test_common_formats_and_holidays(self):
        for text in ("25 December 2026", "Dec 25", "December 25th", "2026-12-25",
                     "the 25th of December", "Christmas", "christmas day"):
            with self.subTest(text=text):
                self.assertEqual(parse_date(text, TODAY).value, date(2026, 12, 25))

    def test_dates_without_a_year_use_the_next_or_latest_occurrence(self):
        self.assertEqual(parse_date("1 March", TODAY).value, date(2027, 3, 1))
        self.assertEqual(parse_date("1 March", TODAY, prefer="past").value, date(2026, 3, 1))
        self.assertEqual(parse_date("Halloween", TODAY).value, date(2027, 10, 31))
        self.assertFalse(parse_date("Halloween", TODAY).explicit_year)

    def test_relative_days_and_weekdays(self):
        self.assertEqual(parse_date("tomorrow", TODAY).value, date(2026, 11, 14))
        self.assertEqual(parse_date("next Friday", TODAY).value, date(2026, 11, 20))
        self.assertEqual(parse_date("last Friday", TODAY).value, date(2026, 11, 6))
        self.assertEqual(parse_date("christmas next year", TODAY).value, date(2027, 12, 25))

    def test_impossible_dates_raise_and_unknown_text_is_none(self):
        for text in ("31 February 2027", "29 February 2027", "30 February", "32 May"):
            with self.subTest(text=text), self.assertRaises(DateError):
                parse_date(text, TODAY)
        self.assertIsNone(parse_date("my exam", TODAY))


class DateReplyTests(unittest.TestCase):
    def test_countdown_and_time_since(self):
        self.assertEqual(
            dates.countdown("Christmas", TODAY),
            "There are 42 days (6 weeks) until Christmas (Friday, 25 December 2026).",
        )
        self.assertEqual(dates.countdown("tomorrow", TODAY), "Tomorrow is Saturday, 14 November 2026.")
        self.assertEqual(
            dates.time_since("13 November 2020", TODAY),
            "It has been 2,191 days (6 years) since Friday, 13 November 2020.",
        )

    def test_days_between_keeps_dates_without_a_year_together(self):
        self.assertEqual(
            dates.days_between("1 Jan", "31 Dec", TODAY),
            "There are 364 days (52 weeks) between Friday, 1 January 2027 and "
            "Friday, 31 December 2027.",
        )
        self.assertIn("92 days", dates.days_between("1 March 2026", "1 June", TODAY))
        self.assertIn("7 days", dates.days_between("Christmas", "New Year's Day", TODAY))
        self.assertIn("108 days", dates.days_between("today", "1 March", TODAY))
        self.assertTrue(dates.days_between("24 Dec", "25 Dec", TODAY).startswith("There is 1 day "))

    def test_weekday_of(self):
        self.assertEqual(dates.weekday_of("1 January 2027", TODAY), "1 January 2027 is a Friday.")
        self.assertEqual(
            dates.weekday_of("20 July 1969", TODAY, past=True), "20 July 1969 was a Sunday."
        )

    def test_shifting_keeps_the_day_of_the_month_where_it_can(self):
        self.assertEqual(dates.shift(date(2027, 1, 31), 1, "month"), date(2027, 2, 28))
        self.assertEqual(dates.shift(date(2028, 1, 31), 1, "months"), date(2028, 2, 29))
        self.assertEqual(dates.shift(date(2028, 2, 29), 1, "year"), date(2029, 2, 28))
        self.assertEqual(
            dates.shifted("3", "weeks", TODAY), "3 weeks from today is Friday, 4 December 2026."
        )
        self.assertEqual(
            dates.shifted("30", "days", TODAY, backwards=True),
            "30 days ago was Wednesday, 14 October 2026.",
        )
        self.assertEqual(
            dates.shifted("a", "fortnight", TODAY, base="25 December 2026"),
            "1 fortnight after Friday, 25 December 2026 is Friday, 8 January 2027.",
        )

    def test_age(self):
        self.assertTrue(
            dates.age("5 May 1990", TODAY).startswith("Someone born on Saturday, 5 May 1990 is 36 years old.")
        )
        self.assertTrue(
            dates.age("5 May 1990", TODAY, you=True).startswith(
                "You were born on Saturday, 5 May 1990, so you are 36 years old."
            )
        )
        self.assertEqual(dates.age("13 November 2000", TODAY, you=True), "You turn 26 today. Happy birthday!")
        self.assertIn("36 if their birthday", dates.age("1990", TODAY))
        for text in ("5 May", "1 January 2030"):
            with self.subTest(text=text), self.assertRaises(DateError):
                dates.age(text, TODAY)

    def test_leap_years_and_lengths(self):
        self.assertTrue(dates.leap_year("2000", TODAY).startswith("Yes, 2000 is a leap year"))
        self.assertTrue(dates.leap_year("1900", TODAY).startswith("No, 1900 is not a leap year"))
        self.assertEqual(dates.leap_year(None, TODAY, next_one=True), "The next leap year is 2028.")
        self.assertEqual(dates.month_length("February", "2028", TODAY), "February 2028 has 29 days.")
        self.assertEqual(dates.month_length("April", None, TODAY), "April has 30 days.")
        self.assertEqual(dates.year_length("2027"), "2027 has 365 days.")


if __name__ == "__main__":
    unittest.main()
