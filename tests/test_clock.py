import unittest
from datetime import datetime, timezone
from unittest import mock

from jarvis import clock

NOW = datetime(2026, 11, 13, 20, 36, tzinfo=timezone.utc)


def _has_zone_data() -> bool:
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo("Asia/Tokyo")
    except Exception:  # pragma: no cover - depends on the environment
        return False
    return True


@unittest.skipUnless(_has_zone_data(), "no time zone database is installed")
class WorldClockTests(unittest.TestCase):
    def test_city_time_and_offset_from_you(self):
        self.assertEqual(
            clock.describe_time("Tokyo", NOW),
            "In Tokyo it is 05:36 on Saturday, 14 November (Asia/Tokyo, UTC+09:00). "
            "That is 9 hours ahead of you.",
        )

    def test_daylight_saving_time_is_applied(self):
        self.assertIn("UTC+11:00, daylight saving time", clock.describe_time("Sydney", NOW))
        self.assertIn("15:36", clock.describe_time("New York", NOW))

    def test_countries_zones_and_unknown_places(self):
        self.assertTrue(
            clock.describe_time("Australia", NOW).startswith(
                "In Canberra, the capital of Australia, it is 07:36"
            )
        )
        self.assertTrue(clock.describe_time("UTC", NOW).startswith("It is 20:36 on Friday, 13 November in UTC."))
        self.assertIn("05:36", clock.describe_time("asia/tokyo", NOW))
        with self.assertRaises(clock.ClockError):
            clock.describe_time("Narnia", NOW)

    def test_time_difference(self):
        self.assertEqual(
            clock.describe_difference("London", "Tokyo", NOW),
            "London is 9 hours behind Tokyo. It is 20:36 on Friday, 13 November in "
            "London and 05:36 on Saturday, 14 November in Tokyo.",
        )
        self.assertIn(
            "5 hours and 30 minutes ahead of the United Kingdom",
            clock.describe_difference("India", "UK", NOW),
        )
        self.assertIn("keep the same time", clock.describe_difference("Lisbon", "London", NOW))


class WorldClockFallbackTests(unittest.TestCase):
    def test_standard_offset_is_used_without_zone_data(self):
        with mock.patch.object(clock, "ZoneInfo", side_effect=KeyError("Asia/Tokyo")):
            reply = clock.describe_time("Tokyo", NOW)
        self.assertTrue(reply.startswith("In Tokyo it is about 05:36"))
        self.assertIn("daylight saving time is not applied", reply)


if __name__ == "__main__":
    unittest.main()
