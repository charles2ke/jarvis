"""Tests for the live weather and hazard feeds ported from 5-Mins.

Every request goes to a fake opener: these tests never use the network.
"""

import http.client
import json
import re
import unittest
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from unittest import mock

from jarvis import alerts, websearch

NOW = datetime(2026, 11, 21, 1, 13, 30, 123456, tzinfo=timezone.utc)
RETRIEVED = "retrieved 2026-11-21 01:13 UTC"
SAFETY_LINE = (
    "Jarvis is not an official warning system — follow your local authorities and official alerts."
)
CREDIT_LINE = "From 5-Mins: https://charles2ke.github.io/5-Mins/"


class FakeHeaders:
    def __init__(self, content_type):
        self._content_type = content_type

    def get_content_charset(self):
        return "utf-8"

    def get_content_type(self):
        return self._content_type

    def get(self, _name, default=None):
        return default


class FakeResponse:
    def __init__(self, payload, content_type="application/json"):
        self._payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.headers = FakeHeaders(content_type)

    def read(self, amount=None):
        return self._payload if amount is None else self._payload[:amount]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeWeb:
    """An opener that answers by URL prefix and records every request."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        for prefix, answer in self.routes:
            if request.full_url.startswith(prefix):
                if isinstance(answer, Exception):
                    raise answer
                return answer() if callable(answer) else answer
        raise urllib.error.URLError("no route")

    def params(self, index=0):
        query = urllib.parse.urlsplit(self.requests[index].full_url).query
        return dict(urllib.parse.parse_qsl(query))

    def sent(self, prefix):
        """The one request to ``prefix``; the hazard feeds are asked in parallel."""

        found = [request for request in self.requests if request.full_url.startswith(prefix)]
        if len(found) != 1:
            raise AssertionError(f"expected one request to {prefix}, got {len(found)}")
        return found[0]

    def query(self, prefix):
        return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.sent(prefix).full_url).query))


def place(name, lat, lon, code, country, admin1, zone, **extra):
    return {
        "name": name, "latitude": lat, "longitude": lon, "country_code": code,
        "country": country, "admin1": admin1, "timezone": zone, **extra,
    }


PARIS = place("Paris", 48.85341, 2.3488, "FR", "France", "Île-de-France", "Europe/Paris")
PARIS_TX = place(
    "Paris", 33.66094, -95.55551, "US", "United States", "Texas", "America/Chicago", admin2="Lamar"
)
MIAMI = place("Miami", 25.77427, -80.19366, "US", "United States", "Florida", "America/New_York")
TOKYO = place("Tokyo", 35.6895, 139.69171, "JP", "Japan", "Tokyo", "Asia/Tokyo")
TORONTO = place("Toronto", 43.70011, -79.4163, "CA", "Canada", "Ontario", "America/Toronto")


def found(*results):
    return FakeResponse({"results": list(results)})


FORECAST = {
    "timezone": "Europe/Paris",
    "timezone_abbreviation": "CET",
    "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h", "precipitation": "mm"},
    "current": {
        "time": "2026-11-21T02:00", "temperature_2m": 12.4, "apparent_temperature": 9.6,
        "relative_humidity_2m": 81, "precipitation": 0.4, "weather_code": 61,
        "wind_speed_10m": 15.2, "is_day": 0,
    },
    "daily": {
        "time": ["2026-11-21"], "temperature_2m_max": [14.5], "temperature_2m_min": [5.5],
        "precipitation_probability_max": [80],
    },
}


def forecast(**current):
    payload = json.loads(json.dumps(FORECAST))
    payload["current"].update(current)
    return FakeResponse(payload)


def ms(text):
    """Milliseconds since 1970 for a UTC time, as USGS sends them."""

    return int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp() * 1000)


def point(lat, lon):
    return {"type": "Point", "coordinates": [lon, lat]}


def feed(*features):
    return FakeResponse({"type": "FeatureCollection", "features": list(features)})


def quake(ident, mag, when, lat=25.77427, lon=-80.19366, title=None):
    return {
        "id": ident,
        "type": "Feature",
        "properties": {
            "mag": mag, "place": "Miami, Florida", "time": ms(when),
            "title": title or f"M {mag} - Miami, Florida",
        },
        "geometry": {"type": "Point", "coordinates": [lon, lat, 10.0]},
    }


def disaster(kind, ident, level, name, lat, lon, country=""):
    return {
        "type": "Feature",
        "geometry": point(lat, lon),
        "properties": {
            "eventtype": kind, "eventid": ident, "alertlevel": level, "name": name,
            "country": country, "fromdate": "2026-11-18T00:00:00", "todate": "2026-11-21T00:00:00",
        },
    }


FLOOD_WATCH = {
    "id": "https://api.weather.gov/alerts/urn:oid:2.49.0.1.840.0.1",
    "type": "Feature",
    "properties": {
        "id": "urn:oid:2.49.0.1.840.0.1",
        "areaDesc": "Coastal Miami-Dade",
        "effective": "2026-11-20T17:00:00-05:00",
        "expires": "2026-11-21T19:00:00-05:00",
        "severity": "Moderate",
        "event": "Flood Watch",
        "headline": "Flood Watch issued November 20 by NWS Miami FL",
    },
}
WILDFIRE = {
    "id": "EONET_9001",
    "title": "Wildfire North of Miami",
    "description": None,
    "closed": None,
    "categories": [{"id": "wildfires", "title": "Wildfires"}],
    "sources": [{"id": "InciWeb", "url": "https://inciweb.example/9001"}],
    # Only the latest position is near Miami, and it is neither first nor last.
    "geometry": [
        {"date": "2026-11-15T00:00:00Z", "type": "Point", "coordinates": [-80.19366, 40.0]},
        {"date": "2026-11-20T12:00:00Z", "type": "Point", "coordinates": [-80.19366, 28.77427]},
        {"date": "2026-11-17T00:00:00Z", "type": "Point", "coordinates": [-80.19366, 41.0]},
    ],
}
FAR_VOLCANO = {
    "id": "EONET_9002",
    "title": "Volcano in Japan",
    "categories": [{"title": "Volcanoes"}],
    "geometry": [{"date": "2026-11-20T00:00:00Z", "coordinates": [139.0, 35.0]}],
}
EMPTY_FEED = feed()
NO_EVENTS = FakeResponse({"events": []})


def hazard_web(geocoding=found(MIAMI), nws=EMPTY_FEED, usgs=EMPTY_FEED, gdacs=EMPTY_FEED,
               eonet=NO_EVENTS):
    return FakeWeb(
        [
            (alerts.GEOCODING_ENDPOINT, geocoding),
            (alerts.NWS_ENDPOINT, nws),
            (alerts.USGS_ENDPOINT, usgs),
            (alerts.GDACS_ENDPOINT, gdacs),
            (alerts.EONET_ENDPOINT, eonet),
        ]
    )


def space(code, issued, body):
    return {
        "product_id": code,
        "issue_datetime": issued,
        "message": f"Space Weather Message Code: {code}\r\nSerial Number: 1\r\n\r\n{body}\r\n",
    }


class OfflineTestCase(unittest.TestCase):
    def setUp(self):
        # A request that bypasses the fake opener fails the test instead of going online.
        patcher = mock.patch("urllib.request.urlopen", side_effect=AssertionError("network used"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def assertSigned(self, reply):
        self.assertEqual(reply.splitlines()[-2:], [SAFETY_LINE, CREDIT_LINE])


class GeocodeTests(OfflineTestCase):
    def test_sends_only_the_encoded_name_and_takes_the_first_usable_result(self):
        unusable = [{"name": "Paris"}, {"name": "", "latitude": 1, "longitude": 1},
                    {"name": "Paris", "latitude": 91, "longitude": 0}, "junk"]
        web = FakeWeb([(alerts.GEOCODING_ENDPOINT, found(*unusable, PARIS))])
        paris = alerts.geocode("Paris&count=1#frag", opener=web)
        self.assertEqual(
            (paris.label, paris.coordinates, paris.country_code, paris.timezone),
            ("Paris, Île-de-France, France", "48.85°N, 2.35°E", "FR", "Europe/Paris"),
        )
        request = web.requests[0]
        self.assertEqual(urllib.parse.urlsplit(request.full_url).netloc, "geocoding-api.open-meteo.com")
        self.assertIn("?name=Paris%26count%3D1%23frag&", request.full_url)
        self.assertEqual(web.params()["count"], "10")
        self.assertEqual(request.get_header("User-agent"), websearch.USER_AGENT)

    def test_rejects_unusable_input_without_a_request(self):
        web = FakeWeb([])
        for text, message in (
            ("", "Please name a place"),
            ("  ?! ", "Please name a place"),
            ("x, France", "Please name a place"),
            ("near me", "does not know where you are"),
            ("Here?", "does not know where you are"),
            ("a" * 101, "too long"),
            ("95, 10", "out of range"),
        ):
            with self.subTest(text=text), self.assertRaisesRegex(alerts.AlertsError, message):
                alerts.geocode(text, opener=web)
        self.assertEqual(web.requests, [])

    def test_unknown_places_are_reported(self):
        for payload in ({"generationtime_ms": 0.4}, {"results": "none"}):
            with self.subTest(payload=payload):
                web = FakeWeb([(alerts.GEOCODING_ENDPOINT, FakeResponse(payload))])
                with self.assertRaisesRegex(
                    alerts.AlertsError, r"^I could not find a place called 'Atlantis'\. "
                ):
                    alerts.geocode("Atlantis", opener=web)
                self.assertEqual(len(web.requests), 1)

    def test_a_region_or_country_after_a_comma_must_match(self):
        web = FakeWeb([(alerts.GEOCODING_ENDPOINT, found(PARIS, PARIS_TX))])
        for text, region in (
            ("Paris", "Île-de-France"),
            ("Paris, Texas", "Texas"),
            ("Paris, TX", "Texas"),
            ("Paris, USA", "Texas"),
            ("Paris, Lamar, Texas", "Texas"),
            ("Paris, france", "Île-de-France"),
        ):
            with self.subTest(text=text):
                self.assertEqual(alerts.geocode(text, opener=web).admin1, region)
        with self.assertRaisesRegex(alerts.AlertsError, "could not find a place called 'Paris, Narnia'"):
            alerts.geocode("Paris, Narnia", opener=web)
        self.assertEqual({web.params(index)["name"] for index in range(len(web.requests))}, {"Paris"})

    def test_coordinates_need_no_lookup(self):
        web = FakeWeb([])
        north = alerts.geocode("40.7128, -74.006", opener=web)
        self.assertEqual((north.latitude, north.longitude, north.label), (40.7128, -74.006, "40.71°N, 74.01°W"))
        south = alerts.geocode("33.9°S 151.2°E", opener=web)
        self.assertEqual((south.latitude, south.longitude), (-33.9, 151.2))
        self.assertEqual(web.requests, [])

    def test_retries_without_a_leading_the(self):
        philippines = place("Philippines", 13.0, 122.0, "PH", "Philippines", "", "Asia/Manila")
        web = FakeWeb(
            [
                (alerts.GEOCODING_ENDPOINT + "?name=the+", found()),
                (alerts.GEOCODING_ENDPOINT, found(philippines)),
            ]
        )
        self.assertEqual(alerts.geocode("the Philippines", opener=web).label, "Philippines")
        self.assertEqual([web.params(0)["name"], web.params(1)["name"]], ["the Philippines", "Philippines"])


class WeatherTests(OfflineTestCase):
    def test_reports_current_conditions_and_todays_range(self):
        web = FakeWeb([(alerts.GEOCODING_ENDPOINT, found(PARIS)), (alerts.FORECAST_ENDPOINT, forecast())])
        reply = alerts.weather("Paris", opener=web, now=NOW)
        self.assertEqual(
            reply,
            "\n".join(
                [
                    "Weather in Paris, Île-de-France, France (48.85°N, 2.35°E):",
                    "- Now: Light rain, 12°C (54°F), feels like 10°C (49°F).",
                    "- Today: high 15°C (58°F), low 6°C (42°F), 80% chance of precipitation.",
                    "- Wind 15 km/h (9 mph), humidity 81%, recent precipitation 0.4 mm.",
                    "- As of 02:00 local time on 21 Nov 2026 (CET).",
                    "",
                    f"Sources: Open-Meteo geocoding and forecast (weather-model data), {RETRIEVED}.",
                    SAFETY_LINE,
                    CREDIT_LINE,
                ]
            ),
        )
        params = web.query(alerts.FORECAST_ENDPOINT)
        self.assertEqual(
            (params["latitude"], params["longitude"], params["timezone"]), ("48.85341", "2.3488", "auto")
        )
        self.assertIn("weather_code", params["current"])
        self.assertIn("precipitation_probability_max", params["daily"])
        self.assertEqual(web.sent(alerts.FORECAST_ENDPOINT).get_header("Accept"), "application/json")

    def test_names_clear_nights_and_rough_weather(self):
        for current, line in (
            ({"weather_code": 0, "is_day": 0}, "- Now: Clear night, 12°C"),
            ({"weather_code": 0, "is_day": 1}, "- Now: Clear sky, 12°C"),
            ({"weather_code": 95, "wind_speed_10m": 45}, "- Rough weather now: thunderstorms and strong wind."),
            ({"weather_code": 66}, "- Rough weather now: freezing rain or drizzle."),
        ):
            with self.subTest(current=current):
                web = FakeWeb([(alerts.FORECAST_ENDPOINT, forecast(**current))])
                reply = alerts.weather("48.85, 2.35", opener=web, now=NOW)
                self.assertTrue(reply.startswith("Weather at 48.85°N, 2.35°E:\n"))
                self.assertIn(line, reply)
                self.assertIn(f"\nSources: Open-Meteo forecast (weather-model data), {RETRIEVED}.\n", reply)
                self.assertSigned(reply)

    def test_copes_with_missing_and_odd_fields(self):
        sparse = {"current": {"temperature_2m": 20, "weather_code": 1234, "time": "soon"},
                  "daily": {"temperature_2m_max": []}}
        web = FakeWeb([(alerts.FORECAST_ENDPOINT, FakeResponse(sparse))])
        reply = alerts.weather("48.85, 2.35", opener=web, now=NOW)
        self.assertEqual(reply.splitlines()[:3], ["Weather at 48.85°N, 2.35°E:", "- Now: 20°C (68°F).", ""])
        # Impossible readings are left out rather than shown.
        absurd = {"current": {"temperature_2m": 1e308, "relative_humidity_2m": 140, "wind_speed_10m": -5,
                              "weather_code": 3}}
        web = FakeWeb([(alerts.FORECAST_ENDPOINT, FakeResponse(absurd))])
        reply = alerts.weather("48.85, 2.35", opener=web, now=NOW)
        self.assertEqual(reply.splitlines()[:3], ["Weather at 48.85°N, 2.35°E:", "- Now: Overcast.", ""])
        for payload in ({}, {"current": "none"}, []):
            with self.subTest(payload=payload):
                web = FakeWeb([(alerts.FORECAST_ENDPOINT, FakeResponse(payload))])
                with self.assertRaisesRegex(
                    alerts.AlertsError, r"^Open-Meteo sent no current weather for 48\.85°N, 2\.35°E\.$"
                ):
                    alerts.weather("48.85, 2.35", opener=web, now=NOW)

    def test_network_failures_become_readable_errors(self):
        for answer, message in (
            (
                urllib.error.HTTPError(alerts.FORECAST_ENDPOINT, 503, "busy", {}, None),
                r"^Open-Meteo refused the request \(HTTP 503\)\.$",
            ),
            (urllib.error.URLError("timed out"), r"^Open-Meteo could not be reached \(timed out\)\.$"),
            # The server's bad status line is quoted without its escape codes.
            (http.client.BadStatusLine("\x1b[2Jbad"), r"^Open-Meteo could not be reached \(\[2Jbad\)\.$"),
            (FakeResponse(b"<html>"), r"^Open-Meteo sent a reply I could not read\.$"),
        ):
            with self.subTest(message=message):
                web = FakeWeb([(alerts.FORECAST_ENDPOINT, answer)])
                with self.assertRaisesRegex(alerts.AlertsError, message):
                    alerts.weather("48.85, 2.35", opener=web, now=NOW)

    def test_oversized_replies_are_refused(self):
        web = FakeWeb([(alerts.FORECAST_ENDPOINT, forecast())])
        with mock.patch.object(websearch, "MAX_RESPONSE_BYTES", 10):
            with self.assertRaisesRegex(alerts.AlertsError, r"^Open-Meteo sent more data than I can read\.$"):
                alerts.weather("48.85, 2.35", opener=web, now=NOW)


class HazardTests(OfflineTestCase):
    def test_asks_every_feed_for_a_us_place_and_ranks_the_alerts(self):
        web = hazard_web(
            nws=feed(FLOOD_WATCH),
            usgs=feed(
                quake("us6000small", 4.6, "2026-11-20T03:00:00"),
                quake("us6000big", 6.2, "2026-11-19T06:30:00", lat=26.77427,
                      title="M 6.2 - 111 km N of Miami, Florida"),
            ),
            gdacs=feed(
                disaster("TC", 1001, "Orange", "Tropical Cyclone ALPHA-26", 27.77427, -80.19366, "Bahamas"),
                disaster("EQ", 1002, "Red", "Earthquake in Japan", 35.7, 139.7, "Japan"),
            ),
            eonet=FakeResponse({"events": [WILDFIRE, FAR_VOLCANO]}),
        )
        reply = alerts.hazards("Miami", opener=web, now=NOW)
        self.assertEqual(
            reply,
            "\n".join(
                [
                    "Hazard alerts near Miami, Florida, United States (25.77°N, 80.19°W) from the "
                    "last 7 days, most severe first:",
                    "- Magnitude 6.2 earthquake (Severe), 111 km away, 19 Nov 06:30 UTC",
                    "  M 6.2 - 111 km N of Miami, Florida — USGS",
                    "- Tropical cyclone (Severe), 222 km away, 18 Nov 00:00 to 21 Nov 00:00 UTC",
                    "  Tropical Cyclone ALPHA-26 (Bahamas) — GDACS",
                    "- Flood Watch (Moderate), covers this location, 20 Nov 22:00 to 22 Nov 00:00 UTC",
                    "  Flood Watch issued November 20 by NWS Miami FL (Coastal Miami-Dade) — NWS",
                    "- Magnitude 4.6 earthquake (Minor), less than 1 km away, 20 Nov 03:00 UTC",
                    "  M 4.6 - Miami, Florida — USGS",
                    "- Wildfires (severity unknown), 334 km away, 20 Nov 12:00 UTC",
                    "  Wildfire North of Miami — NASA EONET",
                    "",
                    "Searched: NWS alerts for this point; USGS earthquakes of magnitude 4.5+ within "
                    "300 km; GDACS disaster alerts within 1000 km; NASA EONET natural events within "
                    "1000 km.",
                    f"Sources: Open-Meteo geocoding, NWS, USGS, GDACS and NASA EONET, {RETRIEVED}.",
                    SAFETY_LINE,
                    CREDIT_LINE,
                ]
            ),
        )
        self.assertEqual(
            web.query(alerts.NWS_ENDPOINT),
            {
                "point": "25.7743,-80.1937", "start": "2026-11-14T01:13:30Z",
                "end": "2026-11-21T01:13:30Z", "status": "actual", "message_type": "alert",
                "limit": "500",
            },
        )
        self.assertEqual(
            web.query(alerts.USGS_ENDPOINT),
            {
                "format": "geojson", "latitude": "25.77427", "longitude": "-80.19366",
                "maxradiuskm": "300", "minmagnitude": "4.5",
                "starttime": "2026-11-14T01:13:30.123Z", "orderby": "time",
            },
        )
        self.assertEqual(web.query(alerts.GDACS_ENDPOINT), {"fromdate": "2026-11-14", "todate": "2026-11-21"})
        self.assertEqual(web.query(alerts.EONET_ENDPOINT), {"status": "open", "days": "7"})
        nws = web.sent(alerts.NWS_ENDPOINT)
        self.assertEqual(nws.get_header("Accept"), "application/geo+json, application/json")
        self.assertEqual(nws.get_header("User-agent"), websearch.USER_AGENT)
        # The place name goes to the geocoder only; the feeds get coordinates.
        self.assertEqual(
            [request.full_url for request in web.requests if "Miami" in request.full_url],
            [web.sent(alerts.GEOCODING_ENDPOINT).full_url],
        )

    def test_nws_is_only_asked_about_us_points(self):
        for text, geocoding, first_line in (
            (
                "Tokyo", found(TOKYO),
                "No alerts found from USGS, GDACS or NASA EONET near Tokyo, Japan "
                "(35.69°N, 139.69°E) in the last 7 days.",
            ),
            (
                # Inside the box NWS covers, but in Canada.
                "Toronto", found(TORONTO),
                "No alerts found from USGS, GDACS or NASA EONET near Toronto, Ontario, Canada "
                "(43.70°N, 79.42°W) in the last 7 days.",
            ),
            (
                "25.77, -80.19", AssertionError("coordinates need no geocoding"),
                "No alerts found from NWS, USGS, GDACS or NASA EONET near 25.77°N, 80.19°W in the "
                "last 7 days.",
            ),
        ):
            with self.subTest(text=text):
                reply = alerts.hazards(text, opener=hazard_web(geocoding=geocoding), now=NOW)
                self.assertEqual(reply.splitlines()[0], first_line)
                self.assertSigned(reply)
        self.assertIn(f"\nSources: NWS, USGS, GDACS and NASA EONET, {RETRIEVED}.\n", reply)

    def test_a_failing_feed_does_not_hide_the_others(self):
        web = hazard_web(
            nws=urllib.error.HTTPError(alerts.NWS_ENDPOINT, 400, "Bad Request", {}, None),
            usgs=urllib.error.URLError("timed out"),
            gdacs=FakeResponse(b""),
            eonet=FakeResponse({"events": [WILDFIRE]}),
        )
        reply = alerts.hazards("Miami", opener=web, now=NOW)
        self.assertEqual(
            reply.splitlines()[1:9],
            [
                "- Wildfires (severity unknown), 334 km away, 20 Nov 12:00 UTC",
                "  Wildfire North of Miami — NASA EONET",
                "",
                "Some feeds did not answer, so this list may be incomplete:",
                "- NWS refused the request (HTTP 400). It only covers US locations.",
                "- USGS could not be reached (timed out).",
                "- GDACS sent a reply I could not read.",
                "",
            ],
        )
        self.assertIn("\nSearched: NASA EONET natural events within 1000 km.\n", reply)
        self.assertIn(f"\nSources: Open-Meteo geocoding and NASA EONET, {RETRIEVED}.\n", reply)
        self.assertSigned(reply)

    def test_says_so_when_no_feed_answers(self):
        web = hazard_web(
            nws=urllib.error.URLError("down"), usgs=urllib.error.URLError("down"),
            gdacs=urllib.error.URLError("down"), eonet=urllib.error.URLError("down"),
        )
        reply = alerts.hazards("25.77, -80.19", opener=web, now=NOW)
        self.assertEqual(
            reply,
            "\n".join(
                [
                    "I can't tell whether there are hazard alerts near 25.77°N, 80.19°W, because "
                    "none of the feeds answered:",
                    "- NWS could not be reached (down).",
                    "- USGS could not be reached (down).",
                    "- GDACS could not be reached (down).",
                    "- NASA EONET could not be reached (down).",
                    "",
                    "Sources: none answered (tried 2026-11-21 01:13 UTC).",
                    SAFETY_LINE,
                    CREDIT_LINE,
                ]
            ),
        )

    def test_lists_the_eight_most_severe_and_recent_once_each(self):
        quakes = [
            quake(f"us{n}", round(4.5 + n / 10, 1), f"2026-11-{14 + n % 7}T12:00:00") for n in range(10)
        ]
        # A repeated id keeps the first report, so this one is not shown as Extreme.
        repeat = quake("us9", 7.5, "2026-11-20T12:00:00")
        reply = alerts.hazards("Miami", opener=hazard_web(usgs=feed(*quakes, repeat)), now=NOW)
        shown = re.findall(r"^- Magnitude (\S+) earthquake \((\w+)\)", reply, re.MULTILINE)
        self.assertEqual(
            shown,
            [("5.1", "Moderate"), ("5.0", "Moderate"), ("5.4", "Moderate"), ("5.3", "Moderate"),
             ("5.2", "Moderate"), ("4.9", "Minor"), ("4.8", "Minor"), ("4.7", "Minor")],
        )
        self.assertIn("\nShowing the 8 most severe and recent of 10 alerts.\n", reply)

    def test_odd_entries_are_cleaned_or_skipped(self):
        storm = {
            "properties": {
                "event": "Storm\u202e Warning",
                "severity": "Catastrophic",
                "headline": "<b>Storm</b> &lt;script&gt;alert(1)&lt;/script&gt; ahead\x1b[2J "
                + "very " * 40,
                "effective": "not a date",
            }
        }
        shapeless = {
            "id": "us-odd",
            "properties": {"mag": None, "time": "yesterday"},
            "geometry": {"coordinates": [-80.19, 500]},
        }
        web = hazard_web(
            nws=feed("junk", None, storm, 7),
            usgs=feed(shapeless),
            gdacs=FakeResponse({"features": "none"}),
            eonet=FakeResponse({"events": [None, {"geometry": "none"}]}),
        )
        reply = alerts.hazards("Miami", opener=web, now=NOW)
        lines = reply.splitlines()
        self.assertEqual(lines[1], "- Storm Warning (severity unknown), covers this location, time unknown")
        self.assertTrue(lines[2].startswith("  Storm alert(1) ahead[2J very very"))
        self.assertTrue(lines[2].endswith("very… — NWS"))
        self.assertLess(len(lines[2]), 120)
        self.assertEqual(
            lines[3:5], ["- Earthquake (severity unknown), distance unknown, time unknown", "  Earthquake — USGS"]
        )
        for unwanted in ("<", ">", "\x1b", "\u202e"):
            self.assertNotIn(unwanted, reply)
        self.assertNotIn("did not answer", reply)


class SpaceWeatherTests(OfflineTestCase):
    def test_lists_recent_alerts_newest_first_with_noaa_scales(self):
        storm = space("ALTK07", "2026-11-20 18:30:00.000", "ALERT: Geomagnetic K-index of 7\r\nNOAA Scale: G3 - Strong")
        entries = [
            space("ALTEF3", "2026-11-20 06:10:00.000", "ALERT: Electron 2MeV Integral Flux exceeded 1000pfu"),
            space("WARK05", "2026-11-20 12:00:00.000",
                  "WARNING: Geomagnetic K-index of 5 expected\r\nNOAA Scale: G1 - Minor"),
            storm,
            storm,
            space("SUMX01", "2026-11-20 20:00:00.000", "SUMMARY: X-ray Event exceeded X1\r\nNOAA Scale: R3 - Strong"),
            space("WARK04", "2026-11-13 23:59:00.000", "WARNING: Geomagnetic K-index of 4 expected"),
            "junk",
            {"issue_datetime": "2026-11-20 21:00:00.000"},
        ]
        web = FakeWeb([(alerts.SWPC_ENDPOINT, FakeResponse(entries))])
        reply = alerts.space_weather(opener=web, now=NOW)
        self.assertEqual(
            reply,
            "\n".join(
                [
                    "Latest NOAA space weather alerts, watches and warnings (last 7 days, newest first):",
                    "- 20 Nov 18:30 UTC — Alert (G3 Strong): Geomagnetic K-index of 7",
                    "- 20 Nov 12:00 UTC — Warning (G1 Minor): Geomagnetic K-index of 5 expected",
                    "- 20 Nov 06:10 UTC — Alert: Electron 2MeV Integral Flux exceeded 1000pfu",
                    "NOAA scales: G = geomagnetic storm, S = solar radiation storm, R = radio blackout; "
                    "1 is minor and 5 extreme.",
                    "",
                    f"Sources: NOAA Space Weather Prediction Center, {RETRIEVED}.",
                    SAFETY_LINE,
                    CREDIT_LINE,
                ]
            ),
        )
        self.assertEqual(len(web.requests), 1)

    def test_caps_the_list_and_says_when_there_is_nothing(self):
        watches = [
            space(f"WATA{n}", f"2026-11-{14 + n} 12:00:00.000", "WATCH: Geomagnetic storm watch")
            for n in range(7)
        ]
        reply = alerts.space_weather(opener=FakeWeb([(alerts.SWPC_ENDPOINT, FakeResponse(watches))]), now=NOW)
        lines = reply.splitlines()
        self.assertEqual(lines[1], "- 20 Nov 12:00 UTC — Watch: Geomagnetic storm watch")
        self.assertTrue(lines[5].startswith("- 16 Nov 12:00 UTC"))
        self.assertEqual(lines[6], "Showing the 5 newest of 7.")
        self.assertNotIn("NOAA scales", reply)
        for payload in ([], {"alerts": []}):
            with self.subTest(payload=payload):
                web = FakeWeb([(alerts.SWPC_ENDPOINT, FakeResponse(payload))])
                reply = alerts.space_weather(opener=web, now=NOW)
                self.assertEqual(
                    reply.splitlines()[0],
                    "No NOAA space weather alerts, watches or warnings in the last 7 days "
                    "(summaries of past events are left out).",
                )
                self.assertSigned(reply)

    def test_feed_failures_raise_readable_errors(self):
        web = FakeWeb([(alerts.SWPC_ENDPOINT, urllib.error.HTTPError(alerts.SWPC_ENDPOINT, 502, "bad", {}, None))])
        with self.assertRaisesRegex(alerts.AlertsError, r"^NOAA SWPC refused the request \(HTTP 502\)\.$"):
            alerts.space_weather(opener=web, now=NOW)


class UsageTests(unittest.TestCase):
    def test_usage_gives_examples_and_ends_with_the_credit(self):
        text = alerts.usage()
        self.assertIn("'weather in Paris'", text)
        self.assertIn("--web-search", text)
        self.assertEqual(text.splitlines()[-2:], [SAFETY_LINE, CREDIT_LINE])


if __name__ == "__main__":
    unittest.main()
