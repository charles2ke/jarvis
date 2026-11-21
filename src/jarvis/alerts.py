"""Live weather and hazard alerts from free public feeds that need no API key.

Jarvis answers most things offline, but weather and warnings are only useful
when they are current, so these lookups go online:

:func:`weather`
    Current conditions and today's range from the Open-Meteo forecast.
:func:`hazards`
    Alerts from the last seven days near a place. The feeds are asked
    independently, so one failure never hides the others: the US National
    Weather Service (US locations only), USGS earthquakes of magnitude 4.5 or
    more within 300 km, and GDACS disaster alerts and NASA EONET natural
    events within 1000 km.
:func:`space_weather`
    The latest alerts, watches and warnings from the NOAA Space Weather
    Prediction Center.

Places are found with the Open-Meteo geocoding API, or given as ``lat, lon``.
Every reply names its sources and when they were read, and says that Jarvis
is not an official warning system.

Provenance: ported to Python from the author's own 5-Mins project
(https://github.com/charles2ke/5-Mins, live at
https://charles2ke.github.io/5-Mins/), commit
560f23e4fada678e605517d100e5f0a968e490ae, licensed AGPL-3.0. The feeds,
query parameters, radii, severity scales, filtering and ordering follow
``assets/js/alerts.js``. The forecast request and the WMO weather-code labels
follow ``assets/js/weather.js``, and the place lookup follows
``assets/js/cities.js``. As its documentation says, 5-Mins is an
informational tool and does not replace official warning systems. Its
features for warning other people (e-mail, SMS, WhatsApp and share links) and
its safety check-ins were left out on purpose: this module only reads public
feeds and never sends anything.
"""

from __future__ import annotations

import html
import http.client
import json
import math
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, List, Mapping, Optional, Sequence, Tuple

from jarvis import websearch

PROJECT = "5-Mins"
SITE_URL = "https://charles2ke.github.io/5-Mins/"
REPO_URL = "https://github.com/charles2ke/5-Mins"
SOURCE_COMMIT = "560f23e4fada678e605517d100e5f0a968e490ae"
#: The last line of every reply.
CREDIT = f"From {PROJECT}: {SITE_URL}"
SAFETY_NOTE = (
    "Jarvis is not an official warning system — follow your local authorities "
    "and official alerts."
)

GEOCODING_ENDPOINT = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
NWS_ENDPOINT = "https://api.weather.gov/alerts"
USGS_ENDPOINT = "https://earthquake.usgs.gov/fdsnws/event/1/query"
GDACS_ENDPOINT = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
EONET_ENDPOINT = "https://eonet.gsfc.nasa.gov/api/v3/events"
SWPC_ENDPOINT = "https://services.swpc.noaa.gov/products/alerts.json"

#: Alerts are shown for the week leading up to now.
ALERT_WINDOW_DAYS = 7
#: Earthquakes below this magnitude are not treated as a disaster alert.
MIN_MAGNITUDE = 4.5
EARTHQUAKE_RADIUS_KM = 300
#: GDACS and EONET place large events (cyclones, floods, wildfires) at a
#: single point, so they are searched over a wider radius than earthquakes.
GLOBAL_EVENT_RADIUS_KM = 1000
EARTH_RADIUS_KM = 6371.0
#: Wind speeds, in km/h, that make the weather itself worth noticing.
STRONG_WIND_KMH = 40
SEVERITY_ORDER = ("Extreme", "Severe", "Moderate", "Minor", "Unknown")
MAX_ALERTS = 8
MAX_SPACE_ALERTS = 5
MIN_PLACE_CHARS = 2
MAX_PLACE_CHARS = 100

#: WMO weather codes as 5-Mins names them, with the kind of weather drawn.
WEATHER_CODES: Mapping[int, Tuple[str, str]] = {
    0: ("Clear sky", "clear"),
    1: ("Mainly clear", "partly"),
    2: ("Partly cloudy", "partly"),
    3: ("Overcast", "cloud"),
    45: ("Fog", "fog"),
    48: ("Freezing fog", "fog"),
    51: ("Light drizzle", "rain"),
    53: ("Drizzle", "rain"),
    55: ("Heavy drizzle", "rain"),
    56: ("Freezing drizzle", "sleet"),
    57: ("Heavy freezing drizzle", "sleet"),
    61: ("Light rain", "rain"),
    63: ("Rain", "rain"),
    65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "sleet"),
    67: ("Heavy freezing rain", "sleet"),
    71: ("Light snow", "snow"),
    73: ("Snow", "snow"),
    75: ("Heavy snow", "snow"),
    77: ("Snow grains", "snow"),
    80: ("Light rain showers", "rain"),
    81: ("Rain showers", "rain"),
    82: ("Violent rain showers", "rain"),
    85: ("Snow showers", "snow"),
    86: ("Heavy snow showers", "snow"),
    95: ("Thunderstorm", "thunder"),
    96: ("Thunderstorm with hail", "thunder"),
    99: ("Thunderstorm with heavy hail", "thunder"),
}

GDACS_EVENT_TYPES: Mapping[str, str] = {
    "DR": "Drought",
    "EQ": "Earthquake",
    "FL": "Flood",
    "TC": "Tropical cyclone",
    "TS": "Tsunami",
    "VO": "Volcanic activity",
    "WF": "Wildfire",
}

#: Boxes (min lat, max lat, min lon, max lon) the National Weather Service
#: issues alerts for: the mainland, Alaska, the western Aleutians, Hawaii,
#: Puerto Rico and the Virgin Islands, Guam and the Marianas, American Samoa.
#: It answers 400 for points it cannot place in a US zone.
NWS_COVERAGE: Sequence[Tuple[float, float, float, float]] = (
    (23, 50, -127, -64),
    (50, 72, -170, -129),
    (47, 56, 170, 180),
    (15, 24, -163, -152),
    (17, 19, -68, -64),
    (12, 21, 143, 147),
    (-16, -12, -172, -168),
)
_NWS_COUNTRIES = frozenset({"US", "PR", "VI", "GU", "MP", "AS", "UM"})

_JSON = "application/json"
_GEO_JSON = "application/geo+json, application/json"
_KMH_PER_MPH = 1.609344
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_EVENT_CHARS = 60
_HEADLINE_CHARS = 110
_AREA_CHARS = 40
_FORECAST_CURRENT = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,"
    "weather_code,wind_speed_10m,is_day"
)
_FORECAST_DAILY = "temperature_2m_max,temperature_2m_min,precipitation_probability_max"
#: Beyond Earth's records in °C or °F; a reading outside it is treated as missing.
_TEMPERATURE_RANGE = (-150, 150)
_ROUGH_KINDS = {"thunder": "thunderstorms", "snow": "snow", "sleet": "freezing rain or drizzle"}
_GDACS_LEVELS = {"red": "Extreme", "orange": "Severe", "green": "Minor"}
_SPACE_KINDS = {
    "ALERT": "Alert",
    "WARNING": "Warning",
    "WATCH": "Watch",
    "EXTENDED WARNING": "Extended warning",
    "CANCEL WARNING": "Warning cancelled",
}
#: NOAA's own word for each level of its G, S and R scales.
_NOAA_LEVELS = {1: "Minor", 2: "Moderate", 3: "Strong", 4: "Severe", 5: "Extreme"}
_SCALE_NOTE = (
    "NOAA scales: G = geomagnetic storm, S = solar radiation storm, "
    "R = radio blackout; 1 is minor and 5 extreme."
)


class AlertsError(websearch.WebSearchError):
    """Raised when a lookup cannot be done; the message is a full sentence."""


@dataclass(frozen=True)
class Place:
    """A place to look up, as the Open-Meteo geocoding API describes it.

    A place given as coordinates has empty names.
    """

    name: str
    admin1: str
    country: str
    country_code: str
    latitude: float
    longitude: float
    timezone: str

    @property
    def label(self) -> str:
        """``Name, Region, Country`` without repeats, or the coordinates."""

        parts: List[str] = []
        for part in (self.name, self.admin1, self.country):
            if part and _fold(part) not in {_fold(seen) for seen in parts}:
                parts.append(part)
        return ", ".join(parts) or self.coordinates

    @property
    def coordinates(self) -> str:
        lat, lon = self.latitude, self.longitude
        return f"{abs(lat):.2f}°{'S' if lat < 0 else 'N'}, {abs(lon):.2f}°{'W' if lon < 0 else 'E'}"


@dataclass(frozen=True)
class Alert:
    """One hazard from a feed, in the common shape 5-Mins gives them."""

    id: str
    feed: str
    event: str
    severity: str
    headline: str
    area: str
    effective: Optional[datetime]
    expires: Optional[datetime]
    distance_km: Optional[float] = None
    covers_place: bool = False


@dataclass(frozen=True)
class _SpaceAlert:
    issued: datetime
    kind: str
    #: The highest NOAA scale level the message names, such as "G3 Strong".
    scale: str
    text: str


@dataclass(frozen=True)
class _Feed:
    name: str
    scope: str
    url: str
    read: Callable[[object, Place], List[Alert]]
    hints: Mapping[int, str] = field(default_factory=dict)


# --- Text and numbers --------------------------------------------------------

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG = re.compile(r"</?[A-Za-z][^<>]*>|<![^<>]*>")


def _one_line(value: object) -> str:
    return re.sub(r"\s+", " ", websearch.clean_text(value)).strip()


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    if space > limit * 2 // 3:
        cut = cut[:space]
    return cut.rstrip(" ,;:-") + "…"


def _plain(value: object, limit: int) -> str:
    """Feed text as one short line: no markup, control characters or runs of spaces."""

    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return ""
    text = _TAG.sub(" ", _HTML_COMMENT.sub(" ", str(value)))
    # Escaped tags such as &lt;b&gt; only become tags once unescaped.
    text = _TAG.sub(" ", html.unescape(text))
    return _cap(_one_line(text), limit)


def _fold(value: object) -> str:
    """``value`` for comparison: no accents, case or punctuation."""

    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"[^\W_]+", text.casefold()))


def _join(items: Sequence[str], conjunction: str = "and") -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} {conjunction} {items[-1]}"


def _number(value: object) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value.strip() if isinstance(value, str) else value)
    except (ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _reading(value: object, low: float, high: float) -> Optional[float]:
    """A forecast number, or ``None`` when it is missing or physically implausible."""

    number = _number(value)
    return number if number is not None and low <= number <= high else None


def _round(value: float) -> int:
    """Round half up, as JavaScript's ``Math.round`` does."""

    return math.floor(value + 0.5)


def _fixed(value: float, places: int) -> str:
    """``value`` with ``places`` decimals, rounded as JavaScript's ``toFixed`` does."""

    quantum = Decimal(1).scaleb(-places)
    return format(Decimal(value).quantize(quantum, rounding=ROUND_HALF_UP), "f")


def _js_number(value: float) -> str:
    """``value`` as JavaScript's ``String(number)`` writes a coordinate."""

    if value == int(value):
        return str(int(value))
    return format(Decimal(repr(value)), "f")


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle (haversine) distance in kilometres."""

    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def _first_coordinate(coordinates: object, _depth: int = 0) -> Optional[Tuple[float, float]]:
    """The first ``(lon, lat)`` of a GeoJSON point, line or polygon."""

    if not isinstance(coordinates, list) or _depth > 6:
        return None
    if len(coordinates) >= 2 and all(
        isinstance(value, (int, float)) and not isinstance(value, bool) for value in coordinates[:2]
    ):
        lon, lat = _number(coordinates[0]), _number(coordinates[1])
        return (lon, lat) if lon is not None and lat is not None and -90 <= lat <= 90 else None
    for entry in coordinates:
        found = _first_coordinate(entry, _depth + 1)
        if found:
            return found
    return None


def _distance_from(place: Place, point: Optional[Tuple[float, float]]) -> Optional[float]:
    if point is None:
        return None
    return _distance_km(place.latitude, place.longitude, point[1], point[0])


# --- Time --------------------------------------------------------------------

_ISO_TIME = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})"
    r"(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?)?"
    r"\s*(Z|[+-]\d{2}(?::?\d{2})?)?",
    re.IGNORECASE | re.ASCII,
)
_LOCAL_TIME = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", re.ASCII)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse_time(value: object) -> Optional[datetime]:
    """A feed timestamp in UTC, or ``None``.

    Numbers are milliseconds since 1970, as USGS sends them. Like 5-Mins, a
    time without a zone (GDACS, SWPC) and a bare date are read as UTC.
    """

    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)):
            return _EPOCH + timedelta(milliseconds=value) if math.isfinite(value) else None
        match = _ISO_TIME.fullmatch(value.strip()) if isinstance(value, str) else None
        if not match:
            return None
        year, month, day, hour, minute, second, fraction, zone = match.groups()
        micro = int((fraction or "0")[:6].ljust(6, "0"))
        parsed = datetime(
            int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0),
            micro, tzinfo=timezone.utc,
        )
        if zone and zone.upper() != "Z":
            digits = zone[1:].replace(":", "")
            hours, minutes = int(digits[:2]), int(digits[2:] or 0)
            if hours > 23 or minutes > 59:
                return None
            offset = timedelta(hours=hours, minutes=minutes)
            parsed = parsed - offset if zone[0] == "+" else parsed + offset
        return parsed
    except (ValueError, OverflowError):
        return None


def _time_value(value: object) -> float:
    parsed = _parse_time(value)
    return parsed.timestamp() if parsed else -math.inf


def _utc_now(now: Optional[datetime]) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    return now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)


def _stamp(moment: datetime) -> str:
    return f"{moment:%Y-%m-%d %H:%M} UTC"


def _short_time(moment: datetime, now: datetime) -> str:
    """``20 Nov 22:00``, with the year only when it is not this year's."""

    year = f" {moment.year}" if moment.year != now.year else ""
    return f"{moment.day} {_MONTHS[moment.month - 1]}{year} {moment:%H:%M}"


def _period(start: Optional[datetime], end: Optional[datetime], now: datetime) -> str:
    if start and end and end != start:
        return f"{_short_time(start, now)} to {_short_time(end, now)} UTC"
    if start:
        return f"{_short_time(start, now)} UTC"
    if end:
        return f"until {_short_time(end, now)} UTC"
    return "time unknown"


# --- HTTP --------------------------------------------------------------------


def _get_json(
    url: str,
    *,
    service: str,
    opener: Optional[websearch.Opener],
    timeout: float,
    accept: str = _JSON,
    hints: Optional[Mapping[int, str]] = None,
) -> object:
    request = urllib.request.Request(
        url, headers={"User-Agent": websearch.USER_AGENT, "Accept": accept}
    )
    fetch = opener or urllib.request.urlopen
    try:
        with fetch(request, timeout=timeout) as response:
            payload = response.read(websearch.MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        hint = (hints or {}).get(exc.code, "")
        raise AlertsError(
            f"{service} refused the request (HTTP {exc.code}).{' ' + hint if hint else ''}"
        ) from exc
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as exc:
        # The reason can quote the server's own bytes, such as a bad status line.
        reason = _one_line(getattr(exc, "reason", None) or exc)[:200] or exc.__class__.__name__
        raise AlertsError(f"{service} could not be reached ({reason}).") from exc
    if len(payload) > websearch.MAX_RESPONSE_BYTES:
        raise AlertsError(f"{service} sent more data than I can read.")
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8-sig", errors="replace")
    try:
        return json.loads(payload)
    except (ValueError, RecursionError) as exc:
        raise AlertsError(f"{service} sent a reply I could not read.") from exc


def _footer(sources: Sequence[str], now: datetime) -> List[str]:
    if sources:
        line = f"Sources: {_join(sources)}, retrieved {_stamp(now)}."
    else:
        line = f"Sources: none answered (tried {_stamp(now)})."
    return ["", line, SAFETY_NOTE, CREDIT]


# --- Places ------------------------------------------------------------------

_COORDINATES = re.compile(
    r"(?P<lat>[+-]?\d{1,2}(?:\.\d+)?)\s*°?\s*(?P<ns>[NS])?\s*(?:,|\s)\s*"
    r"(?P<lon>[+-]?\d{1,3}(?:\.\d+)?)\s*°?\s*(?P<ew>[EW])?",
    re.IGNORECASE | re.ASCII,
)
_NOT_PLACES = frozenset(
    {
        "here", "me", "near me", "around me", "around here", "my location", "my area",
        "my city", "my town", "where i am", "outside", "now", "today", "tonight", "tomorrow",
    }
)
_COUNTRY_ALIASES = {
    "usa": "us", "u s": "us", "u s a": "us", "america": "us", "united states of america": "us",
    "uk": "gb", "u k": "gb", "britain": "gb", "great britain": "gb", "uae": "ae",
}
_US_STATES = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas", "ca": "california",
    "co": "colorado", "ct": "connecticut", "de": "delaware", "fl": "florida", "ga": "georgia",
    "hi": "hawaii", "id": "idaho", "il": "illinois", "in": "indiana", "ia": "iowa",
    "ks": "kansas", "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland",
    "ma": "massachusetts", "mi": "michigan", "mn": "minnesota", "ms": "mississippi",
    "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada", "nh": "new hampshire",
    "nj": "new jersey", "nm": "new mexico", "ny": "new york", "nc": "north carolina",
    "nd": "north dakota", "oh": "ohio", "ok": "oklahoma", "or": "oregon", "pa": "pennsylvania",
    "ri": "rhode island", "sc": "south carolina", "sd": "south dakota", "tn": "tennessee",
    "tx": "texas", "ut": "utah", "vt": "vermont", "va": "virginia", "wa": "washington",
    "wv": "west virginia", "wi": "wisconsin", "wy": "wyoming", "dc": "district of columbia",
    "d c": "district of columbia",
}


def _clean_place(place: object) -> str:
    text = _one_line(place).strip(" \"'`“”‘’?!.,;:")
    if len(text) > MAX_PLACE_CHARS:
        raise AlertsError(
            f"That place name is too long; please keep it under {MAX_PLACE_CHARS} characters."
        )
    if _fold(text) in _NOT_PLACES:
        raise AlertsError(
            "Jarvis does not know where you are, so please name a place, for example "
            "'weather in Paris'."
        )
    if len(text) < MIN_PLACE_CHARS:
        raise AlertsError(
            "Please name a place, for example 'weather in Paris' or 'hazards near Manila'."
        )
    return text


def _parse_coordinates(text: str) -> Optional[Tuple[float, float]]:
    match = _COORDINATES.fullmatch(text)
    if not match:
        return None
    lat, lon = float(match["lat"]), float(match["lon"])
    if (match["ns"] or "").upper() == "S":
        lat = -abs(lat)
    if (match["ew"] or "").upper() == "W":
        lon = -abs(lon)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise AlertsError(
            "Those coordinates are out of range: latitude runs from -90 to 90 and "
            "longitude from -180 to 180."
        )
    return lat, lon


def _to_place(result: object) -> Optional[Place]:
    """A geocoding result as a :class:`Place`, if it is usable (as in cities.js)."""

    if not isinstance(result, dict):
        return None
    name = _plain(result.get("name"), 80)
    lat, lon = _number(result.get("latitude")), _number(result.get("longitude"))
    if not name or lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    code = _plain(result.get("country_code"), 3).upper()
    return Place(
        name=name,
        admin1=_plain(result.get("admin1"), 80),
        country=_plain(result.get("country"), 80),
        country_code=code if re.fullmatch(r"[A-Z]{2}", code) else "",
        latitude=lat,
        longitude=lon,
        timezone=_plain(result.get("timezone"), 64),
    )


def _qualifies(result: Mapping[str, object], qualifier: str) -> bool:
    """True when ``qualifier`` ("Texas", "TX", "France", "UK") names the result's region."""

    wanted = _fold(qualifier)
    code = _fold(result.get("country_code"))
    names = {
        _fold(result.get(key))
        for key in ("admin1", "admin2", "admin3", "admin4", "country", "country_code")
    }
    names.discard("")
    return (
        wanted in names
        or _COUNTRY_ALIASES.get(wanted) == code
        or (code == "us" and _US_STATES.get(wanted) == _fold(result.get("admin1")))
    )


def _lookup(
    name: str, qualifiers: Sequence[str], *, opener: Optional[websearch.Opener], timeout: float
) -> Optional[Place]:
    params = {"name": name, "count": "10", "language": "en", "format": "json"}
    payload = _get_json(
        f"{GEOCODING_ENDPOINT}?{urllib.parse.urlencode(params)}",
        service="Open-Meteo",
        opener=opener,
        timeout=timeout,
    )
    results = payload.get("results") if isinstance(payload, dict) else None
    for result in results if isinstance(results, list) else []:
        found = _to_place(result)
        if found and all(_qualifies(result, qualifier) for qualifier in qualifiers):
            return found
    return None


def geocode(
    place: str,
    *,
    opener: Optional[websearch.Opener] = None,
    timeout: float = websearch.DEFAULT_TIMEOUT,
    now: Optional[datetime] = None,
) -> Place:
    """Find ``place`` with the Open-Meteo geocoding API; the first match wins.

    ``place`` can be a name ("Nairobi"), a name with its region or country
    ("Paris, Texas", "Miami, FL"), which then must match, or coordinates
    ("48.85, 2.35"), which need no lookup. Only the name is sent, URL-encoded.
    Raises :class:`AlertsError` when nothing matches. ``now`` is unused; it
    is accepted so every lookup takes the same arguments.
    """

    query = _clean_place(place)
    point = _parse_coordinates(query)
    if point is not None:
        return Place("", "", "", "", point[0], point[1], "")
    parts = [part.strip() for part in query.split(",") if part.strip()]
    name, qualifiers = parts[0], parts[1:4]
    if len(name) < MIN_PLACE_CHARS:
        raise AlertsError(
            "Please name a place, for example 'weather in Paris' or 'hazards near Manila'."
        )
    found = _lookup(name, qualifiers, opener=opener, timeout=timeout)
    # "the Philippines": GeoNames has no leading article, while "The Hague" does.
    article = re.fullmatch(r"the\s+(.{2,})", name, re.IGNORECASE)
    if found is None and article:
        found = _lookup(article.group(1), qualifiers, opener=opener, timeout=timeout)
    if found is None:
        raise AlertsError(
            f"I could not find a place called '{_cap(query, 60)}'. Check the spelling, or "
            "add the country, as in 'Paris, France'."
        )
    return found


def _where(place: Place) -> str:
    return f"{place.label} ({place.coordinates})" if place.name else place.coordinates


# --- Weather -----------------------------------------------------------------


def _describe(code: object, is_day: bool) -> Tuple[Optional[str], str]:
    """The label and kind for a WMO code; the label is ``None`` when unknown."""

    number = _number(code)
    found = WEATHER_CODES.get(int(number)) if number is not None and number.is_integer() else None
    if found is None:
        return None, "cloud"
    label, kind = found
    if kind == "clear" and not is_day:
        return "Clear night", "night"
    return label, kind


def _temperature(value: float, unit: str) -> str:
    if unit == "°C":
        return f"{_round(value)}°C ({_round(value * 9 / 5 + 32)}°F)"
    if unit == "°F":
        return f"{_round(value)}°F ({_round((value - 32) * 5 / 9)}°C)"
    return f"{_round(value)}{unit}"


def _speed(value: float, unit: str) -> str:
    if unit == "km/h":
        return f"{_round(value)} km/h ({_round(value / _KMH_PER_MPH)} mph)"
    if unit in ("mp/h", "mph"):
        return f"{_round(value)} mph ({_round(value * _KMH_PER_MPH)} km/h)"
    return f"{_round(value)} {unit}"


def _amount(value: float) -> str:
    text = f"{_round(value * 10) / 10:.1f}"
    return text[:-2] if text.endswith(".0") else text


def _first(values: object) -> object:
    return values[0] if isinstance(values, list) and values else None


def _local_time(value: object) -> Optional[str]:
    match = _LOCAL_TIME.match(value) if isinstance(value, str) else None
    if not match:
        return None
    try:
        moment = datetime(*(int(part) for part in match.groups()))
    except ValueError:
        return None
    return f"{moment:%H:%M} local time on {moment.day} {_MONTHS[moment.month - 1]} {moment.year}"


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def _weather_lines(payload: object, place: Place) -> List[str]:
    data = _mapping(payload)
    current = _mapping(data.get("current"))
    units = _mapping(data.get("current_units"))
    daily = _mapping(data.get("daily"))
    flag = _number(current.get("is_day"))
    label, kind = _describe(current.get("weather_code"), flag is None or flag == 1)
    temperature = _reading(current.get("temperature_2m"), *_TEMPERATURE_RANGE)
    feels = _reading(current.get("apparent_temperature"), *_TEMPERATURE_RANGE)
    humidity = _reading(current.get("relative_humidity_2m"), 0, 100)
    rain = _reading(current.get("precipitation"), 0, 1000)
    wind = _reading(current.get("wind_speed_10m"), 0, 1000)
    if label is None and temperature is None and wind is None and humidity is None:
        raise AlertsError(f"Open-Meteo sent no current weather for {place.label}.")
    temp_unit = _plain(units.get("temperature_2m"), 8) or "°C"
    wind_unit = _plain(units.get("wind_speed_10m"), 8) or "km/h"
    rain_unit = _plain(units.get("precipitation"), 8) or "mm"

    lines = []
    now = [label] if label else []
    if temperature is not None:
        now.append(_temperature(temperature, temp_unit))
    if feels is not None:
        now.append(f"feels like {_temperature(feels, temp_unit)}")
    if now:
        lines.append(f"- Now: {', '.join(now)}.")

    today = []
    high = _reading(_first(daily.get("temperature_2m_max")), *_TEMPERATURE_RANGE)
    low = _reading(_first(daily.get("temperature_2m_min")), *_TEMPERATURE_RANGE)
    chance = _reading(_first(daily.get("precipitation_probability_max")), 0, 100)
    if high is not None:
        today.append(f"high {_temperature(high, temp_unit)}")
    if low is not None:
        today.append(f"low {_temperature(low, temp_unit)}")
    if chance is not None:
        today.append(f"{_round(chance)}% chance of precipitation")
    if today:
        lines.append(f"- Today: {', '.join(today)}.")

    details = []
    if wind is not None:
        details.append(f"wind {_speed(wind, wind_unit)}")
    if humidity is not None:
        details.append(f"humidity {_round(humidity)}%")
    if rain is not None:
        details.append(f"recent precipitation {_amount(rain)} {rain_unit}")
    if details:
        text = ", ".join(details)
        lines.append(f"- {text[0].upper()}{text[1:]}.")

    rough = [_ROUGH_KINDS[kind]] if kind in _ROUGH_KINDS else []
    if wind is not None and wind_unit == "km/h" and wind >= STRONG_WIND_KMH:
        rough.append("strong wind")
    if rough:
        lines.append(f"- Rough weather now: {_join(rough)}.")

    observed = _local_time(current.get("time"))
    if observed:
        zone = _plain(data.get("timezone_abbreviation"), 16) or _plain(data.get("timezone"), 40)
        lines.append(f"- As of {observed}{f' ({zone})' if zone else ''}.")
    return lines


def weather(
    place: str,
    *,
    opener: Optional[websearch.Opener] = None,
    timeout: float = websearch.DEFAULT_TIMEOUT,
    now: Optional[datetime] = None,
) -> str:
    """The current weather and today's range at ``place``, from Open-Meteo.

    Temperatures are in °C with °F, wind in km/h with mph. Raises
    :class:`AlertsError` when the place or the forecast cannot be found.
    """

    when = _utc_now(now)
    found = geocode(place, opener=opener, timeout=timeout)
    params = {
        "latitude": _js_number(found.latitude),
        "longitude": _js_number(found.longitude),
        "current": _FORECAST_CURRENT,
        "daily": _FORECAST_DAILY,
        "timezone": "auto",
        "forecast_days": "1",
    }
    payload = _get_json(
        f"{FORECAST_ENDPOINT}?{urllib.parse.urlencode(params)}",
        service="Open-Meteo",
        opener=opener,
        timeout=timeout,
    )
    lines = [f"Weather {'in' if found.name else 'at'} {_where(found)}:"]
    lines += _weather_lines(payload, found)
    source = "Open-Meteo geocoding and forecast" if found.name else "Open-Meteo forecast"
    return "\n".join(lines + _footer([f"{source} (weather-model data)"], when))


# --- Hazard feeds (ported from 5-Mins' alerts.js) ------------------------------


def _features(payload: object) -> List[Mapping[str, object]]:
    features = payload.get("features") if isinstance(payload, dict) else None
    return [item for item in features if isinstance(item, dict)] if isinstance(features, list) else []


def _ident(*candidates: object) -> str:
    for candidate in candidates:
        if isinstance(candidate, (str, int, float)) and not isinstance(candidate, bool) and candidate:
            return str(candidate)
    return ""


def _read_nws(payload: object, place: Place) -> List[Alert]:
    found = []
    for index, feature in enumerate(_features(payload)):
        props = _mapping(feature.get("properties"))
        severity = props.get("severity")
        found.append(
            Alert(
                id=_ident(props.get("id"), feature.get("id")) or f"nws-{index}",
                feed="NWS",
                event=_plain(props.get("event"), _EVENT_CHARS) or "Weather alert",
                severity=severity if severity in SEVERITY_ORDER else "Unknown",
                headline=_plain(props.get("headline") or props.get("description"), _HEADLINE_CHARS),
                area=_plain(props.get("areaDesc"), _AREA_CHARS),
                effective=_parse_time(props.get("effective") or props.get("onset")),
                expires=_parse_time(props.get("expires") or props.get("ends")),
                covers_place=True,
            )
        )
    return found


def _magnitude_severity(magnitude: Optional[float]) -> str:
    if magnitude is None:
        return "Unknown"
    if magnitude >= 7:
        return "Extreme"
    if magnitude >= 6:
        return "Severe"
    if magnitude >= 5:
        return "Moderate"
    return "Minor"


def _read_usgs(payload: object, place: Place) -> List[Alert]:
    found = []
    for index, feature in enumerate(_features(payload)):
        props = _mapping(feature.get("properties"))
        magnitude = _number(props.get("mag"))
        if magnitude is not None and not -10 < magnitude < 12:
            magnitude = None
        point = _first_coordinate(_mapping(feature.get("geometry")).get("coordinates"))
        found.append(
            Alert(
                id=_ident(feature.get("id")) or f"usgs-{index}",
                feed="USGS",
                event=(
                    f"Magnitude {_fixed(magnitude, 1)} earthquake"
                    if magnitude is not None
                    else "Earthquake"
                ),
                severity=_magnitude_severity(magnitude),
                headline=_plain(props.get("title") or props.get("place"), _HEADLINE_CHARS),
                area=_plain(props.get("place"), _AREA_CHARS),
                effective=_parse_time(props.get("time")),
                expires=None,
                distance_km=_distance_from(place, point),
            )
        )
    return found


def _read_gdacs(payload: object, place: Place) -> List[Alert]:
    found = []
    for index, feature in enumerate(_features(payload)):
        point = _first_coordinate(_mapping(feature.get("geometry")).get("coordinates"))
        distance = _distance_from(place, point)
        if distance is None or distance > GLOBAL_EVENT_RADIUS_KM:
            continue
        props = _mapping(feature.get("properties"))
        event_id = _ident(props.get("eventid"))
        event_type = props.get("eventtype")
        found.append(
            Alert(
                id=f"gdacs-{_ident(event_type) or 'XX'}-{event_id}" if event_id else f"gdacs-{index}",
                feed="GDACS",
                event=GDACS_EVENT_TYPES.get(event_type, "Disaster")
                if isinstance(event_type, str)
                else "Disaster",
                severity=_GDACS_LEVELS.get(str(props.get("alertlevel") or "").lower(), "Unknown"),
                headline=_plain(
                    props.get("name")
                    or props.get("description")
                    or _mapping(props.get("severitydata")).get("severitytext"),
                    _HEADLINE_CHARS,
                ),
                area=_plain(props.get("country"), _AREA_CHARS),
                effective=_parse_time(props.get("fromdate")),
                expires=_parse_time(props.get("todate")),
                distance_km=distance,
            )
        )
    return found


def _read_eonet(payload: object, place: Place) -> List[Alert]:
    events = payload.get("events") if isinstance(payload, dict) else None
    found = []
    for index, event in enumerate(events if isinstance(events, list) else []):
        if not isinstance(event, dict):
            continue
        # Events are tracked over time, so use the most recently dated position.
        latest: Optional[Mapping[str, object]] = None
        point: Optional[Tuple[float, float]] = None
        geometries = event.get("geometry")
        for geometry in geometries if isinstance(geometries, list) else []:
            here = _first_coordinate(_mapping(geometry).get("coordinates"))
            if here and (latest is None or _time_value(geometry.get("date")) > _time_value(latest.get("date"))):
                latest, point = geometry, here
        distance = _distance_from(place, point)
        if latest is None or distance is None or distance > GLOBAL_EVENT_RADIUS_KM:
            continue
        categories = event.get("categories")
        category = _mapping(categories[0]) if isinstance(categories, list) and categories else {}
        event_id = _ident(event.get("id"))
        found.append(
            Alert(
                id=f"eonet-{event_id}" if event_id else f"eonet-{index}",
                feed="NASA EONET",
                event=_plain(category.get("title"), _EVENT_CHARS) or "Natural event",
                # EONET tracks confirmed natural events but publishes no severity.
                severity="Unknown",
                headline=_plain(event.get("title"), _HEADLINE_CHARS),
                area=_plain(event.get("description"), _AREA_CHARS),
                effective=_parse_time(latest.get("date")),
                expires=_parse_time(event.get("closed")),
                distance_km=distance,
            )
        )
    return found


def _nws_covers(place: Place) -> bool:
    if place.country_code and place.country_code not in _NWS_COUNTRIES:
        return False
    return any(
        min_lat <= place.latitude <= max_lat and min_lon <= place.longitude <= max_lon
        for min_lat, max_lat, min_lon, max_lon in NWS_COVERAGE
    )


def _nws_point(value: float) -> str:
    """At most four decimals, as NWS demands, written as 5-Mins writes them."""

    text = _fixed(value, 4).rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _iso_millis(moment: datetime) -> str:
    """As JavaScript's ``toISOString``: UTC, milliseconds and ``Z``."""

    return f"{moment:%Y-%m-%dT%H:%M:%S}.{moment.microsecond // 1000:03d}Z"


def _hazard_feeds(place: Place, now: datetime) -> List[_Feed]:
    start = now - timedelta(days=ALERT_WINDOW_DAYS)
    feeds = []
    if _nws_covers(place):
        nws = {
            "point": f"{_nws_point(place.latitude)},{_nws_point(place.longitude)}",
            # NWS rejects timestamps with milliseconds.
            "start": f"{start:%Y-%m-%dT%H:%M:%S}Z",
            "end": f"{now:%Y-%m-%dT%H:%M:%S}Z",
            "status": "actual",
            "message_type": "alert",
            "limit": "500",
        }
        feeds.append(
            _Feed(
                "NWS",
                "NWS alerts for this point",
                f"{NWS_ENDPOINT}?{urllib.parse.urlencode(nws)}",
                _read_nws,
                {400: "It only covers US locations."},
            )
        )
    usgs = {
        "format": "geojson",
        "latitude": _js_number(place.latitude),
        "longitude": _js_number(place.longitude),
        "maxradiuskm": str(EARTHQUAKE_RADIUS_KM),
        "minmagnitude": str(MIN_MAGNITUDE),
        "starttime": _iso_millis(start),
        "orderby": "time",
    }
    gdacs = {"fromdate": f"{start:%Y-%m-%d}", "todate": f"{now:%Y-%m-%d}"}
    eonet = {"status": "open", "days": str(ALERT_WINDOW_DAYS)}
    feeds += [
        _Feed(
            "USGS",
            f"USGS earthquakes of magnitude {MIN_MAGNITUDE}+ within {EARTHQUAKE_RADIUS_KM} km",
            f"{USGS_ENDPOINT}?{urllib.parse.urlencode(usgs)}",
            _read_usgs,
        ),
        _Feed(
            "GDACS",
            f"GDACS disaster alerts within {GLOBAL_EVENT_RADIUS_KM} km",
            f"{GDACS_ENDPOINT}?{urllib.parse.urlencode(gdacs)}",
            _read_gdacs,
        ),
        _Feed(
            "NASA EONET",
            f"NASA EONET natural events within {GLOBAL_EVENT_RADIUS_KM} km",
            f"{EONET_ENDPOINT}?{urllib.parse.urlencode(eonet)}",
            _read_eonet,
        ),
    ]
    return feeds


def _ask_feed(
    feed: _Feed, place: Place, opener: Optional[websearch.Opener], timeout: float
) -> Tuple[List[Alert], Optional[str]]:
    """The feed's alerts, or the sentence saying why it could not be read."""

    try:
        payload = _get_json(
            feed.url, service=feed.name, opener=opener, timeout=timeout, accept=_GEO_JSON,
            hints=feed.hints,
        )
        return feed.read(payload, place), None
    except AlertsError as exc:
        return [], str(exc)
    except (TypeError, ValueError, AttributeError, KeyError, IndexError, ArithmeticError,
            RecursionError):
        # The feed changed its shape in a way the reader did not foresee.
        return [], f"{feed.name} sent a reply I could not read."


def _ranked(found: Sequence[Sequence[Alert]]) -> List[Alert]:
    """Alerts without repeats, most severe first and then newest first."""

    seen, alerts = set(), []
    for batch in found:
        for alert in batch:
            if alert.id not in seen:
                seen.add(alert.id)
                alerts.append(alert)

    def order(alert: Alert) -> Tuple[int, float]:
        rank = SEVERITY_ORDER.index(alert.severity)
        return rank, -(alert.effective.timestamp() if alert.effective else -math.inf)

    return sorted(alerts, key=order)


def _alert_lines(alert: Alert, now: datetime) -> List[str]:
    if alert.covers_place:
        distance = "covers this location"
    elif alert.distance_km is None:
        distance = "distance unknown"
    elif alert.distance_km < 1:
        distance = "less than 1 km away"
    else:
        distance = f"{_round(alert.distance_km)} km away"
    severity = "severity unknown" if alert.severity == "Unknown" else alert.severity
    detail = alert.headline
    if alert.area and _fold(alert.area) not in _fold(detail):
        detail = f"{detail} ({alert.area})" if detail else alert.area
    return [
        f"- {alert.event} ({severity}), {distance}, "
        f"{_period(alert.effective, alert.expires, now)}",
        f"  {detail or alert.event} — {alert.feed}",
    ]


def hazards(
    place: str,
    *,
    opener: Optional[websearch.Opener] = None,
    timeout: float = websearch.DEFAULT_TIMEOUT,
    now: Optional[datetime] = None,
) -> str:
    """Hazard alerts from the last seven days near ``place``.

    Asks NWS (US locations only), USGS, GDACS and NASA EONET at the same time.
    A feed that fails is listed at the end instead of hiding the others'
    alerts. Raises :class:`AlertsError` only when the place cannot be found.
    """

    when = _utc_now(now)
    found = geocode(place, opener=opener, timeout=timeout)
    feeds = _hazard_feeds(found, when)
    with ThreadPoolExecutor(max_workers=len(feeds)) as pool:
        results = list(pool.map(lambda feed: _ask_feed(feed, found, opener, timeout), feeds))
    answered = [feed for feed, (_, error) in zip(feeds, results) if error is None]
    errors = [error for _, error in results if error]
    alerts = _ranked([batch for batch, _ in results])
    where = _where(found)

    if alerts:
        lines = [
            f"Hazard alerts near {where} from the last {ALERT_WINDOW_DAYS} days, "
            "most severe first:"
        ]
        for alert in alerts[:MAX_ALERTS]:
            lines += _alert_lines(alert, when)
        if len(alerts) > MAX_ALERTS:
            lines.append(
                f"Showing the {MAX_ALERTS} most severe and recent of {len(alerts)} alerts."
            )
    elif answered:
        names = _join([feed.name for feed in answered], "or")
        lines = [f"No alerts found from {names} near {where} in the last {ALERT_WINDOW_DAYS} days."]
    else:
        lines = [
            f"I can't tell whether there are hazard alerts near {where}, because none of "
            "the feeds answered:"
        ]
    if errors:
        if answered:
            lines += ["", "Some feeds did not answer, so this list may be incomplete:"]
        lines += [f"- {error}" for error in errors]
    footer = _footer(
        (["Open-Meteo geocoding"] if found.name else []) + [feed.name for feed in answered], when
    )
    if answered:
        footer.insert(1, f"Searched: {'; '.join(feed.scope for feed in answered)}.")
    return "\n".join(lines + footer)


# --- Space weather -----------------------------------------------------------

_SPACE_MESSAGE = re.compile(
    r"^\s*(ALERT|WARNING|WATCH|SUMMARY|EXTENDED WARNING|CANCEL WARNING)\s*:\s*(.+)$",
    re.MULTILINE,
)
_SPACE_SCALE = re.compile(r"\b[GRS]([1-5])\b", re.ASCII)


def _read_swpc(payload: object, now: datetime) -> List[_SpaceAlert]:
    cutoff = now - timedelta(days=ALERT_WINDOW_DAYS)
    seen, found = set(), []
    for index, entry in enumerate(payload if isinstance(payload, list) else []):
        if not isinstance(entry, dict):
            continue
        issued = _parse_time(entry.get("issue_datetime"))
        if issued is None or issued < cutoff:
            continue
        message = entry.get("message")
        text = websearch.clean_text(message) if isinstance(message, str) else ""
        match = _SPACE_MESSAGE.search(text)
        # Summaries describe events that are already over.
        if not match or match.group(1) == "SUMMARY":
            continue
        product = _ident(entry.get("product_id"))
        key = f"{product}-{issued.isoformat()}" if product else str(index)
        if key in seen:
            continue
        seen.add(key)
        scale, level = "", 0
        for token in _SPACE_SCALE.finditer(text):
            if int(token.group(1)) > level:
                scale, level = token.group(0), int(token.group(1))
        found.append(
            _SpaceAlert(
                issued,
                _SPACE_KINDS[match.group(1)],
                f"{scale} {_NOAA_LEVELS[level]}" if scale else "",
                _plain(match.group(2), _HEADLINE_CHARS),
            )
        )
    return sorted(found, key=lambda item: item.issued, reverse=True)


def space_weather(
    *,
    opener: Optional[websearch.Opener] = None,
    timeout: float = websearch.DEFAULT_TIMEOUT,
    now: Optional[datetime] = None,
) -> str:
    """The newest NOAA SWPC alerts, watches and warnings from the last seven days.

    Raises :class:`AlertsError` when the feed cannot be read.
    """

    when = _utc_now(now)
    payload = _get_json(
        SWPC_ENDPOINT, service="NOAA SWPC", opener=opener, timeout=timeout, accept=_GEO_JSON
    )
    found = _read_swpc(payload, when)
    shown = found[:MAX_SPACE_ALERTS]
    if not shown:
        lines = [
            f"No NOAA space weather alerts, watches or warnings in the last {ALERT_WINDOW_DAYS} "
            "days (summaries of past events are left out)."
        ]
    else:
        lines = [
            "Latest NOAA space weather alerts, watches and warnings "
            f"(last {ALERT_WINDOW_DAYS} days, newest first):"
        ]
        for item in shown:
            scale = f" ({item.scale})" if item.scale else ""
            text = f": {item.text}" if item.text else ""
            lines.append(f"- {_short_time(item.issued, when)} UTC — {item.kind}{scale}{text}")
        if len(found) > MAX_SPACE_ALERTS:
            lines.append(f"Showing the {MAX_SPACE_ALERTS} newest of {len(found)}.")
        if any(item.scale for item in shown):
            lines.append(_SCALE_NOTE)
    return "\n".join(lines + _footer(["NOAA Space Weather Prediction Center"], when))


def usage() -> str:
    """How to ask for live weather and hazard alerts."""

    return "\n".join(
        [
            "I can read live weather and hazard alerts from free public feeds:",
            "- 'weather in Paris' for the current conditions and today's range",
            "- 'hazards near Manila' or 'any earthquakes near Lima' for alerts from the last "
            f"{ALERT_WINDOW_DAYS} days",
            "- 'space weather' for the latest NOAA alerts, watches and warnings",
            "Name a city, add its region or country ('Paris, Texas'), or give coordinates "
            "('48.85, 2.35').",
            "These go online, so web search must be on: start Jarvis with "
            "'--web-search manual' or '--web-search auto'.",
            "",
            SAFETY_NOTE,
            CREDIT,
        ]
    )
