import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from project_support import ProjectTestCase, fake_project, missing_projects

from jarvis import alerts, projects
from jarvis.alerts import CREDIT, SAFETY_NOTE, AlertsError

NOW = datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc)
SENT_NOW = "2026-11-21T09:00:00.000+00:00"
ASKED_AT = "Asked through 5-Mins at 2026-11-21 09:00 UTC"

# Made-up answers in the shapes bridges/five-mins.mjs returns.
SAMPLETON = {
    "id": "1",
    "name": "Sampleton",
    "country": "United States",
    "region": "Oklahoma, United States",
    "label": "Sampleton, Oklahoma, United States",
    "lat": 35.5,
    "lon": -97.5,
}
WHERE = "Sampleton, Oklahoma, United States (35.50°N, 97.50°W)"
PARISES = [
    {"id": "2", "name": "Paris", "country": "France", "region": "Île-de-France, France",
     "label": "Paris, Île-de-France, France", "lat": 48.85, "lon": 2.35},
    {"id": "3", "name": "Paris", "country": "United States", "region": "Texas, United States",
     "label": "Paris, Texas, United States", "lat": 33.66, "lon": -95.56},
    {"id": "4", "name": "Paris", "country": "United States", "region": "Tennessee, United States",
     "label": "Paris, Tennessee, United States", "lat": 36.3, "lon": -88.33},
]


def _reading(**changes):
    reading = {
        "label": "Grey and damp",
        "temperature": 12.4,
        "feelsLike": 10.6,
        "humidity": 81,
        "precipitation": 0.2,
        "windSpeed": 14.2,
        "high": 14.1,
        "low": 7.9,
        "observedAt": "2026-11-21T03:00",
        "units": {"temperature": "°C", "wind": "km/h", "precipitation": "mm"},
    }
    reading.update(changes)
    return reading


def _weather_answer(place=SAMPLETON, **changes):
    answer = {
        "place": place,
        "lookupError": None,
        "weather": _reading(),
        "error": None,
        "shown": {"temperature": "12°C", "feelsLike": "11°C", "high": "14°C", "low": "8°C"},
        "rough": False,
        "asked": ["places.example", "forecast.example"],
    }
    answer.update(changes)
    return answer


def _alert(event, severity, headline="", area="", effective="2026-11-20T18:00:00.000Z", expires=None):
    return {
        "id": event, "source": "Sample Feed", "event": event, "severity": severity,
        "headline": headline, "area": area, "effective": effective, "expires": expires,
        "url": "https://alerts.example/",
    }


def _hazards_answer(found=(), errors=(), worldwide=0, feeds=5, place=SAMPLETON):
    return {
        "place": place, "lookupError": None, "days": 7, "alerts": list(found),
        "worldwide": worldwide, "errors": list(errors), "feeds": feeds,
        "asked": ["places.example", "feed-a.example", "feed-b.example"],
    }


def _space_answer(found=(), errors=(), feeds=4):
    return {
        "days": 7, "alerts": list(found), "errors": list(errors), "feeds": feeds,
        "asked": ["feed-a.example", "feed-b.example"],
    }


class WeatherTests(unittest.TestCase):
    def ask(self, place, answer):
        with fake_project("5-Mins", {"weather": answer}) as calls:
            return alerts.weather(place, now=NOW).splitlines(), calls

    def test_the_current_weather_with_both_scales(self):
        lines, calls = self.ask("Sampleton", _weather_answer())
        self.assertEqual(calls, [("weather", {"query": "Sampleton"})])
        self.assertEqual(
            lines,
            [
                f"Weather in {WHERE}:",
                "- Now: Grey and damp, 12°C (54°F), feels like 11°C (51°F).",
                "- Today: high 14°C (57°F), low 8°C (46°F).",
                "- Wind 14 km/h (9 mph), humidity 81%, recent precipitation 0.2 mm.",
                "- As of 03:00 local time on 21 Nov 2026.",
                "",
                f"{ASKED_AT}: places.example and forecast.example.",
                SAFETY_NOTE,
                CREDIT,
            ],
        )

    def test_fahrenheit_and_mph_get_celsius_and_kmh_beside_them(self):
        reading = _reading(
            temperature=54.3, feelsLike=51.1, high=57.4, low=46.2, windSpeed=8.8, precipitation=0.1,
            units={"temperature": "°F", "wind": "mp/h", "precipitation": "inch"},
        )
        shown = {"temperature": "54°F", "feelsLike": "51°F", "high": "57°F", "low": "46°F"}
        lines, _ = self.ask("Sampleton", _weather_answer(weather=reading, shown=shown))
        self.assertEqual(lines[1], "- Now: Grey and damp, 54°F (12°C), feels like 51°F (11°C).")
        self.assertEqual(lines[2], "- Today: high 57°F (14°C), low 46°F (8°C).")
        self.assertEqual(lines[3], "- Wind 9 mph (14 km/h), humidity 81%, recent precipitation 0.1 inch.")

    def test_rough_weather_and_missing_readings(self):
        reading = _reading(
            feelsLike=None, high=None, low=None, humidity=None, precipitation=None, observedAt=None
        )
        lines, _ = self.ask("Sampleton", _weather_answer(weather=reading, rough=True))
        self.assertEqual(
            lines[1:4],
            [
                "- Now: Grey and damp, 12°C (54°F).",
                "- Wind 14 km/h (9 mph).",
                "- 5-Mins rates the weather now as rough.",
            ],
        )
        self.assertEqual(lines[4], "")

    def test_no_readings_is_explained(self):
        empty = _reading(temperature=None, feelsLike=None, humidity=None, precipitation=None, windSpeed=None)
        with self.assertRaises(AlertsError) as raised:
            self.ask("Sampleton", _weather_answer(weather=empty))
        self.assertEqual(
            str(raised.exception),
            f"No current weather came through for {WHERE}; please try again later.",
        )

    def test_a_failed_forecast_or_lookup_is_explained(self):
        failed = _weather_answer(weather=None, error="could not be reached (EAI_AGAIN)")
        with self.assertRaises(AlertsError) as raised:
            self.ask("Sampleton", failed)
        self.assertEqual(
            str(raised.exception),
            f"I couldn't get the weather for {WHERE} just now: could not be reached (EAI_AGAIN).",
        )
        lost = _weather_answer(place=None, weather=None, lookupError="no answer within 10 seconds")
        with self.assertRaises(AlertsError) as raised:
            self.ask("Sampleton", lost)
        self.assertEqual(
            str(raised.exception),
            "I couldn't look up 'Sampleton' just now: no answer within 10 seconds.",
        )


class PlaceTests(unittest.TestCase):
    def test_unusable_places_are_refused_without_asking(self):
        for text in ("", "  ?! ", "near me", "Here?", "a" * 101, "95, 10"):
            with self.subTest(text=text[:20]), fake_project("5-Mins", {}) as calls:
                with self.assertRaises(AlertsError):
                    alerts.weather(text, now=NOW)
                self.assertEqual(calls, [])

    def test_an_unknown_place_is_explained(self):
        nowhere = _weather_answer(place=None, weather=None, asked=["places.example"])
        with fake_project("5-Mins", {"weather": nowhere}) as calls:
            with self.assertRaises(AlertsError) as raised:
                alerts.weather("Atlantis", now=NOW)
        self.assertEqual(calls, [("weather", {"query": "Atlantis"})])
        self.assertIn("I could not find a place called 'Atlantis'.", str(raised.exception))

    def test_a_leading_the_is_dropped_when_nothing_is_found(self):
        isles = dict(SAMPLETON, name="Sample Isles", region="", country="", label="Sample Isles")

        def answer(payload):
            return _weather_answer(place=isles if payload["query"] == "Sample Isles" else None)

        with fake_project("5-Mins", {"weather": answer}) as calls:
            reply = alerts.weather("the Sample Isles", now=NOW)
        self.assertEqual([payload["query"] for _, payload in calls], ["the Sample Isles", "Sample Isles"])
        self.assertTrue(reply.startswith("Weather in Sample Isles (35.50°N, 97.50°W):"))

    def test_a_region_or_country_picks_the_place(self):
        listing = {"cities": PARISES, "lookupError": None, "asked": ["places.example"]}
        expected = {
            "Paris, Texas": PARISES[1],
            "Paris, TN": PARISES[2],
            "Paris, U.S.A.": PARISES[1],
            "Paris, France": PARISES[0],
            "Paris, Île-de-France": PARISES[0],
        }
        for text, city in expected.items():
            actions = {"places": listing, "weather": _weather_answer(place=None)}
            with self.subTest(text=text), fake_project("5-Mins", actions) as calls:
                reply = alerts.weather(text, now=NOW)
                self.assertEqual(
                    calls,
                    [
                        ("places", {"query": "Paris", "limit": 10}),
                        ("weather", {"lat": city["lat"], "lon": city["lon"]}),
                    ],
                )
                self.assertTrue(reply.startswith(f"Weather in {city['label']} ("))
                self.assertIn(f"{ASKED_AT}: places.example and forecast.example.", reply)
        with fake_project("5-Mins", {"places": listing}) as calls:
            with self.assertRaises(AlertsError) as raised:
                alerts.weather("Paris, Narnia", now=NOW)
        self.assertEqual(len(calls), 1)
        self.assertIn("could not find a place called 'Paris, Narnia'", str(raised.exception))

    def test_a_failed_place_lookup_is_explained(self):
        listing = {"cities": [], "lookupError": "could not be reached (EAI_AGAIN)", "asked": ["places.example"]}
        with fake_project("5-Mins", {"places": listing}), self.assertRaises(AlertsError) as raised:
            alerts.hazards("Paris, Texas", now=NOW)
        self.assertEqual(
            str(raised.exception),
            "I couldn't look up 'Paris, Texas' just now: could not be reached (EAI_AGAIN).",
        )

    def test_coordinates_are_used_as_they_are(self):
        for text, point, where in (
            ("40.7128, -74.006", {"lat": 40.7128, "lon": -74.006}, "40.71°N, 74.01°W"),
            ("33.9°S 151.2°E", {"lat": -33.9, "lon": 151.2}, "33.90°S, 151.20°E"),
        ):
            answers = {"weather": _weather_answer(place=None)}
            with self.subTest(text=text), fake_project("5-Mins", answers) as calls:
                reply = alerts.weather(text, now=NOW)
                self.assertEqual(calls, [("weather", point)])
                self.assertTrue(reply.startswith(f"Weather at {where}:\n"))


class HazardTests(unittest.TestCase):
    def ask(self, place, answer):
        with fake_project("5-Mins", {"hazards": answer}) as calls:
            return alerts.hazards(place, now=NOW).splitlines(), calls

    def test_alerts_in_the_projects_order_with_the_worldwide_count(self):
        found = [
            _alert("Sample Flood Watch", "Severe", "Rivers may rise", "Sample County",
                   expires="2026-11-22T06:00:00.000Z"),
            _alert("Sample Quake", "Minor", "A small quake near Sampleton", "near Sampleton",
                   effective="2026-11-19T04:30:00.000Z"),
        ]
        lines, calls = self.ask("Sampleton", _hazards_answer(found, worldwide=2))
        self.assertEqual(calls, [("hazards", {"query": "Sampleton", "now": SENT_NOW})])
        self.assertEqual(
            lines,
            [
                f"Hazard alerts near {WHERE} from the last 7 days, most severe first:",
                "- Sample Flood Watch (severity: Severe), 20 Nov 18:00 to 22 Nov 06:00 UTC",
                "  Rivers may rise (Sample County) — Sample Feed",
                "- Sample Quake (severity: Minor), 19 Nov 04:30 UTC",
                "  A small quake near Sampleton — Sample Feed",
                "There are also 2 worldwide alerts, such as space weather; "
                "ask for 'space weather' to see them.",
                "",
                f"{ASKED_AT}: places.example, feed-a.example and feed-b.example.",
                SAFETY_NOTE,
                CREDIT,
            ],
        )

    def test_long_lists_are_cut_and_failed_feeds_listed(self):
        found = [_alert(f"Sample Alert {number}", "Moderate") for number in range(10)]
        errors = ["Feed A: could not be reached (EAI_AGAIN)"]
        lines, _ = self.ask("Sampleton", _hazards_answer(found, errors, worldwide=1))
        self.assertEqual(len([line for line in lines if line.startswith("- Sample Alert")]), alerts.MAX_ALERTS)
        self.assertIn("Showing the first 8 of 10.", lines)
        self.assertIn(
            "There is also 1 worldwide alert, such as space weather; ask for 'space weather' to see it.", lines
        )
        index = lines.index("Some feeds did not answer, so this list may be incomplete:")
        self.assertEqual(lines[index - 1: index + 3], ["", lines[index], f"- {errors[0]}", ""])

    def test_no_alerts_and_no_answers(self):
        lines, _ = self.ask("Sampleton", _hazards_answer())
        self.assertEqual(lines[:2], [f"No hazard alerts near {WHERE} from the last 7 days.", ""])
        errors = [f"Feed {name}: no answer within 10 seconds" for name in "ABCD"]
        lines, _ = self.ask("Sampleton", _hazards_answer(errors=errors, feeds=4))
        self.assertEqual(
            lines[:6],
            [
                f"I can't tell whether there are hazard alerts near {WHERE}, "
                "because none of the feeds answered:",
                *[f"- {error}" for error in errors],
                "",
            ],
        )

    def test_a_region_is_matched_before_the_feeds_are_asked(self):
        listing = {"cities": [SAMPLETON], "lookupError": None, "asked": ["places.example"]}
        actions = {"places": listing, "hazards": _hazards_answer(place=None)}
        with fake_project("5-Mins", actions) as calls:
            alerts.hazards("Sampleton, OK", now=NOW)
        self.assertEqual(
            calls,
            [
                ("places", {"query": "Sampleton", "limit": 10}),
                ("hazards", {"lat": 35.5, "lon": -97.5, "now": SENT_NOW}),
            ],
        )


class SpaceWeatherTests(unittest.TestCase):
    def ask(self, answer):
        with fake_project("5-Mins", {"space_weather": answer}) as calls:
            return alerts.space_weather(now=NOW).splitlines(), calls

    def test_worldwide_alerts_without_their_area(self):
        found = [_alert(f"Sample Solar Alert {number}", "Moderate", "Charged particles", "Worldwide")
                 for number in range(7)]
        lines, calls = self.ask(_space_answer(found))
        self.assertEqual(calls, [("space_weather", {"now": SENT_NOW})])
        self.assertEqual(
            lines[:3],
            [
                "Space weather and other worldwide alerts from the last 7 days, most severe first:",
                "- Sample Solar Alert 0 (severity: Moderate), 20 Nov 18:00 UTC",
                "  Charged particles — Sample Feed",
            ],
        )
        self.assertEqual(len([line for line in lines if line.startswith("- ")]), alerts.MAX_SPACE_ALERTS)
        self.assertIn("Showing the first 5 of 7.", lines)
        self.assertEqual(
            lines[-4:], ["", f"{ASKED_AT}: feed-a.example and feed-b.example.", SAFETY_NOTE, CREDIT]
        )

    def test_none_found_or_none_answered(self):
        lines, _ = self.ask(_space_answer(errors=["Feed A: the reply could not be read"]))
        self.assertEqual(
            lines[:4],
            [
                "No space weather or other worldwide alerts from the last 7 days.",
                "",
                "Some feeds did not answer, so this list may be incomplete:",
                "- Feed A: the reply could not be read",
            ],
        )
        lines, _ = self.ask(_space_answer(errors=["Feed A: down", "Feed B: down"], feeds=2))
        self.assertEqual(
            lines[:3],
            ["I can't tell whether there are space weather alerts, because none of the feeds answered:",
             "- Feed A: down", "- Feed B: down"],
        )


class ProjectProblemTests(unittest.TestCase):
    def test_missing_project_explains_the_setup(self):
        with missing_projects(), self.assertRaises(projects.ProjectUnavailable) as raised:
            alerts.weather("Sampleton", now=NOW)
        self.assertIn("git submodule update --init projects/5-Mins", str(raised.exception))
        self.assertIn("https://charles2ke.github.io/5-Mins/", str(raised.exception))

    def test_unexpected_answers_are_errors(self):
        broken = {
            "weather": (
                None,
                _weather_answer(weather="warm"),
                _weather_answer(weather=_reading(temperature="12")),
                _weather_answer(weather=_reading(units=None)),
                _weather_answer(shown={}),
                _weather_answer(asked=None),
                _weather_answer(place={"name": "Sampleton", "lat": "35.5", "lon": -97.5}),
            ),
            "hazards": (
                _hazards_answer() | {"alerts": "none"},
                _hazards_answer() | {"days": 0},
                _hazards_answer() | {"feeds": -1},
                _hazards_answer() | {"worldwide": "2"},
                _hazards_answer(found=["a quake"]),
            ),
            "space_weather": (None, _space_answer() | {"errors": "oops"}),
        }
        ask = {
            "weather": lambda: alerts.weather("Sampleton", now=NOW),
            "hazards": lambda: alerts.hazards("Sampleton", now=NOW),
            "space_weather": lambda: alerts.space_weather(now=NOW),
        }
        for action, answers in broken.items():
            for answer in answers:
                with self.subTest(action=action, answer=str(answer)[:80]):
                    with fake_project("5-Mins", {action: answer}), self.assertRaises(projects.ProjectError):
                        ask[action]()

    def test_usage_needs_no_project(self):
        with fake_project("5-Mins", {}) as calls:
            lines = alerts.usage().splitlines()
        self.assertEqual(calls, [])
        self.assertIn("web search must be on", " ".join(lines))
        self.assertEqual(lines[-2:], [SAFETY_NOTE, CREDIT])


# Small made-up answers in each public API's format, keyed by host, for the
# fetch fixtures of jarvis.projects (no request leaves the machine).
PLACES_URL = "https://geocoding-api.open-meteo.com/"
FORECAST_URL = "https://api.open-meteo.com/"
GDACS_URL = "https://www.gdacs.org/"
EONET_URL = "https://eonet.gsfc.nasa.gov/"
PLACES = {PLACES_URL: {"results": [
    {"id": 101, "name": "Sampleton", "latitude": 35.5, "longitude": -97.5,
     "country": "United States", "admin1": "Oklahoma"},
]}}
FORECAST = {FORECAST_URL: {
    "current": {"time": "2026-11-21T03:00", "temperature_2m": 12.4, "apparent_temperature": 10.6,
                "relative_humidity_2m": 81, "precipitation": 0.2, "weather_code": 3,
                "wind_speed_10m": 14.2, "is_day": 0},
    "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h", "precipitation": "mm"},
    "daily": {"temperature_2m_max": [14.1], "temperature_2m_min": [7.9]},
}}
FEEDS = {
    "https://api.weather.gov/": {"features": [{"properties": {
        "id": "https://alerts.example/1", "event": "Made-up Storm Warning", "severity": "Severe",
        "headline": "A made-up storm warning for a test", "areaDesc": "Sample County",
        "effective": "2026-11-20T18:00:00+00:00", "expires": "2026-11-21T18:00:00+00:00",
    }}]},
    "https://earthquake.usgs.gov/": {"features": [{
        "id": "test1",
        "properties": {"mag": 4.8, "place": "12 km N of Sampleton",
                       "title": "Made-up quake 12 km N of Sampleton",
                       "time": 1795176000000, "url": "https://quakes.example/test1"},
        "geometry": {"type": "Point", "coordinates": [-97.5, 35.6, 5]},
    }]},
    GDACS_URL: {"features": []},
    EONET_URL: {"events": []},
    "https://services.swpc.noaa.gov/": [
        {"product_id": "TST1", "issue_datetime": "2026-11-20 12:00:00.000",
         "message": "WARNING: Made-up solar storm for a test"},
    ],
}


class AlertsProjectTests(ProjectTestCase):
    """Runs the real 5-Mins code from projects/5-Mins with Node.js on fetch fixtures."""

    project = "5-Mins"

    def answer_with(self, bodies, statuses=None):
        statuses = statuses or {}
        fixtures = {url: {"status": statuses.get(url, 200), "body": body} for url, body in bodies.items()}
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = os.path.join(folder.name, "fixtures.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump(fixtures, file)
        patched = mock.patch.dict(os.environ, {"JARVIS_PROJECTS_FETCH_FIXTURES": path})
        patched.start()
        self.addCleanup(patched.stop)

    def test_weather_by_name(self):
        self.answer_with({**PLACES, **FORECAST})
        lines = alerts.weather("Sampleton", now=NOW).splitlines()
        self.assertEqual(lines[0], f"Weather in {WHERE}:")
        self.assertRegex(lines[1], r"^- Now: .+, 12°C \(54°F\), feels like 11°C \(51°F\)\.$")
        self.assertEqual(
            lines[2:5],
            [
                "- Today: high 14°C (57°F), low 8°C (46°F).",
                "- Wind 14 km/h (9 mph), humidity 81%, recent precipitation 0.2 mm.",
                "- As of 03:00 local time on 21 Nov 2026.",
            ],
        )
        self.assertEqual(lines[-3], f"{ASKED_AT}: geocoding-api.open-meteo.com and api.open-meteo.com.")

    def test_weather_by_coordinates_needs_no_lookup(self):
        self.answer_with(FORECAST)
        reply = alerts.weather("35.5, -97.5", now=NOW)
        self.assertTrue(reply.startswith("Weather at 35.50°N, 97.50°W:\n- Now: "))
        self.assertIn(f"{ASKED_AT}: api.open-meteo.com.", reply)

    def test_weather_problems_are_explained(self):
        self.answer_with({**PLACES, **FORECAST}, {FORECAST_URL: 503})
        with self.assertRaises(AlertsError) as raised:
            alerts.weather("Sampleton", now=NOW)
        self.assertIn(f"I couldn't get the weather for {WHERE} just now", str(raised.exception))
        self.assertIn("503", str(raised.exception))
        self.answer_with({})
        with self.assertRaises(AlertsError) as raised:
            alerts.weather("Sampleton", now=NOW)
        self.assertIn("I couldn't look up 'Sampleton' just now: could not be reached", str(raised.exception))
        self.answer_with({PLACES_URL: {"results": []}})
        with self.assertRaises(AlertsError) as raised:
            alerts.weather("Atlantis", now=NOW)
        self.assertIn("I could not find a place called 'Atlantis'.", str(raised.exception))

    def test_hazards_from_every_feed(self):
        self.answer_with({**PLACES, **FEEDS})
        lines = alerts.hazards("Sampleton", now=NOW).splitlines()
        self.assertEqual(lines[0], f"Hazard alerts near {WHERE} from the last 7 days, most severe first:")
        reply = "\n".join(lines)
        storm = reply.index("Made-up Storm Warning (severity: Severe), 20 Nov 18:00 to 21 Nov 18:00 UTC")
        self.assertIn("  A made-up storm warning for a test (Sample County) — ", reply)
        self.assertLess(storm, reply.index("Made-up quake 12 km N of Sampleton"))
        self.assertNotIn("Made-up solar storm", reply)
        self.assertIn("There is also 1 worldwide alert", reply)
        self.assertNotIn("may be incomplete", reply)
        asked = lines[-3].removeprefix(f"{ASKED_AT}: ").rstrip(".").replace(" and ", ", ").split(", ")
        self.assertEqual(set(asked), {url.split("/")[2] for url in [PLACES_URL, *FEEDS]})

    def test_hazards_when_feeds_fail(self):
        feeds = {url: body for url, body in FEEDS.items() if url != EONET_URL}
        self.answer_with({**PLACES, **feeds}, {GDACS_URL: 503})
        lines = alerts.hazards("Sampleton", now=NOW).splitlines()
        self.assertIn("Made-up Storm Warning (severity: Severe), 20 Nov 18:00 to 21 Nov 18:00 UTC", lines[1])
        index = lines.index("Some feeds did not answer, so this list may be incomplete:")
        failed = lines[index + 1: lines.index("", index)]
        self.assertEqual(len(failed), 2)
        self.assertTrue(any("503" in line for line in failed))
        self.assertTrue(any("could not be reached" in line for line in failed))
        self.answer_with({})
        lines = alerts.hazards("35.5, -97.5", now=NOW).splitlines()
        self.assertEqual(
            lines[0],
            "I can't tell whether there are hazard alerts near 35.50°N, 97.50°W, "
            "because none of the feeds answered:",
        )

    def test_space_weather(self):
        self.answer_with(FEEDS)
        reply = alerts.space_weather(now=NOW)
        self.assertTrue(reply.startswith("Space weather and other worldwide alerts from the last 7 days"))
        self.assertIn("20 Nov 12:00 UTC\n  Made-up solar storm for a test — ", reply)
        self.assertNotIn("Made-up quake", reply)
        self.assertNotIn("may be incomplete", reply)


if __name__ == "__main__":
    unittest.main()
