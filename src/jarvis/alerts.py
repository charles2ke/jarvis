"""Live weather and hazard alerts, read through the user's 5-Mins project.

5-Mins (https://charles2ke.github.io/5-Mins/, source at
https://github.com/charles2ke/5-Mins) is the user's own app for warning people
about disasters near the places they watch, with the weather there. Jarvis
keeps no copy of it: ``bridges/five-mins.mjs`` runs the project's own modules
from the ``projects/5-Mins`` submodule with Node.js, and they look the place
up, read the forecast and ask the public alert feeds themselves. This module
finds the place in the question and words the answer. It only reads: 5-Mins'
features for warning other people are not used, so Jarvis contacts no one.

:func:`weather`
    The current conditions and today's range at a place, with °F or °C and
    mph or km/h beside the forecast's own units.
:func:`hazards`
    The alerts 5-Mins finds for a place, most severe first. A feed that fails
    is listed instead of hiding the others' alerts, and worldwide alerts are
    only counted.
:func:`space_weather`
    The worldwide alerts, such as space weather, that 5-Mins finds along with
    every place's alerts.

A place is a name ("Nairobi"), a name with its region or country ("Paris,
Texas", "Miami, FL"), which then must match, or coordinates ("48.85, 2.35").
Every reply names the hosts that were asked and when, and says that Jarvis is
not an official warning system. A place that can't be found, or a lookup that
fails, raises :class:`AlertsError`, whose message is a full sentence. When the
project or Node.js is missing, :class:`jarvis.projects.ProjectUnavailable` is
raised with setup steps.
"""

from __future__ import annotations

import html
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from jarvis import projects, websearch

PROJECT = "5-Mins"
SITE_URL = projects.PROJECTS[PROJECT].site
REPO_URL = projects.PROJECTS[PROJECT].repo
#: The last line of every reply.
CREDIT = f"From {PROJECT}: {SITE_URL}"
SAFETY_NOTE = (
    "Jarvis is not an official warning system — follow your local authorities "
    "and official alerts."
)
MAX_ALERTS = 8
MAX_SPACE_ALERTS = 5
MAX_PLACE_CHARS = 100
#: How many places to compare when the question names a region or country.
_CANDIDATES = 10

_KMH_PER_MPH = 1.609344
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class AlertsError(websearch.WebSearchError):
    """Raised when a lookup cannot be done; the message is a full sentence."""


@dataclass(frozen=True)
class _Place:
    """Where a reply is about; ``label`` is empty for a place given as coordinates."""

    label: str
    lat: float
    lon: float

    @property
    def where(self) -> str:
        lat, lon = self.lat, self.lon
        point = f"{abs(lat):.2f}°{'S' if lat < 0 else 'N'}, {abs(lon):.2f}°{'W' if lon < 0 else 'E'}"
        return f"{self.label} ({point})" if self.label else point


@dataclass(frozen=True)
class _Alert:
    event: str
    severity: str
    headline: str
    area: str
    source: str
    effective: Optional[datetime]
    expires: Optional[datetime]


@dataclass(frozen=True)
class _Sweep:
    """The alerts from one round of 5-Mins' feeds, in its order."""

    days: int
    alerts: Tuple[_Alert, ...]
    errors: Tuple[str, ...]
    feeds: int

    @property
    def none_answered(self) -> bool:
        return bool(self.errors) and len(self.errors) >= self.feeds


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

    if not isinstance(value, str):
        return ""
    text = _TAG.sub(" ", _HTML_COMMENT.sub(" ", value))
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


def _round(value: float) -> int:
    """``value`` rounded to a whole number, halves up."""

    return math.floor(value + 0.5)


def _amount(value: float) -> str:
    text = f"{_round(value * 10) / 10:.1f}"
    return text[:-2] if text.endswith(".0") else text


def _days(count: int) -> str:
    return f"{count} day{'' if count == 1 else 's'}"


# --- Time --------------------------------------------------------------------


def _utc_now(now: Optional[datetime]) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    return now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)


def _stamp(moment: datetime) -> str:
    return f"{moment:%Y-%m-%d %H:%M} UTC"


def _moment(value: object) -> Optional[datetime]:
    """An ISO time from 5-Mins in UTC, or ``None``."""

    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # Python 3.10 reads an offset but not the "Z" that JavaScript writes.
    if text[-1] in "Zz":
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


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


def _local_time(value: object) -> Optional[str]:
    """``03:00 local time on 21 Nov 2026`` from the forecast's local clock time."""

    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return f"{moment:%H:%M} local time on {moment.day} {_MONTHS[moment.month - 1]} {moment.year}"


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
#: Other ways of writing a country than the name the place lookup gives it.
_COUNTRY_NAMES = {
    "us": "united states", "u s": "united states", "usa": "united states",
    "u s a": "united states", "america": "united states",
    "united states of america": "united states",
    "uk": "united kingdom", "u k": "united kingdom", "gb": "united kingdom",
    "britain": "united kingdom", "great britain": "united kingdom",
    "uae": "united arab emirates",
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
    if not text:
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


def _matches(city: Dict[str, Any], qualifier: str) -> bool:
    """True when ``qualifier`` ("Texas", "TX", "France", "UK") names the city's region or country."""

    wanted = _fold(qualifier)
    country = _fold(city.get("country"))
    region = city.get("region")
    names = {_fold(part) for part in region.split(",")} if isinstance(region, str) else set()
    names.add(country)
    names.discard("")
    return (
        wanted in names
        or (bool(country) and _COUNTRY_NAMES.get(wanted) == country)
        or (country == "united states" and _US_STATES.get(wanted) in names)
    )


# --- 5-Mins' answers ---------------------------------------------------------


def _unusable(what: str) -> projects.ProjectError:
    return projects.ProjectError(f"5-Mins' answer has no usable {what}")


def _record(value: Any, what: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise _unusable(what)
    return value


def _list(value: Any, what: str) -> List[Any]:
    if not isinstance(value, list):
        raise _unusable(what)
    return value


def _number(record: Dict[str, Any], key: str) -> Optional[float]:
    value = record.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _unusable(repr(key))
    return float(value)


def _count(record: Dict[str, Any], key: str, least: int = 0) -> int:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < least:
        raise _unusable(repr(key))
    return value


def _ask(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return _record(projects.call(PROJECT, action, payload), "answer")


def _hosts(answer: Dict[str, Any]) -> List[str]:
    return [host for host in (_plain(item, 80) for item in _list(answer.get("asked"), "hosts")) if host]


def _reason(error: object) -> str:
    return _plain(error, 200).rstrip(".") or "no reason given"


def _check_lookup(answer: Dict[str, Any], query: str) -> None:
    error = answer.get("lookupError")
    if error:
        raise AlertsError(f"I couldn't look up '{_cap(query, 60)}' just now: {_reason(error)}.")


def _place(value: Any) -> _Place:
    city = _record(value, "place")
    lat, lon = _number(city, "lat"), _number(city, "lon")
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise _unusable("place")
    parts: List[str] = []
    for part in _plain(city.get("label"), 160).split(", "):
        if part and _fold(part) not in {_fold(seen) for seen in parts}:
            parts.append(part)
    label = ", ".join(parts) or _plain(city.get("name"), 80)
    if not label:
        raise _unusable("place")
    return _Place(label, lat, lon)


def _at_place(text: str, action: str, extra: Dict[str, Any]) -> Tuple[_Place, Dict[str, Any], List[str]]:
    """Run ``action`` at the place named in ``text``; return the place, answer and hosts asked.

    One bridge call finds the place and runs the action, unless the text names
    a region or country to match: then the places found are compared first. A
    name starting with "the" that finds nothing is tried again without it.
    """

    query = _clean_place(text)
    point = _parse_coordinates(query)
    if point is not None:
        answer = _ask(action, {"lat": point[0], "lon": point[1], **extra})
        return _Place("", *point), answer, _hosts(answer)
    name, *qualifiers = [part.strip() for part in query.split(",") if part.strip()]
    qualifiers = qualifiers[:3]
    names = [name]
    # The place lookup knows "The Hague" with its article but "Philippines" without.
    article = re.fullmatch(r"the\s+(.+)", name, re.IGNORECASE)
    if article:
        names.append(article.group(1))
    asked: List[str] = []
    for candidate in names:
        if qualifiers:
            listing = _ask("places", {"query": candidate, "limit": _CANDIDATES})
            asked += _hosts(listing)
            _check_lookup(listing, query)
            cities = [_record(city, "place") for city in _list(listing.get("cities"), "places")]
            match = next(
                (city for city in cities if all(_matches(city, wanted) for wanted in qualifiers)), None
            )
            if match is None:
                continue
            place = _place(match)
            answer = _ask(action, {"lat": place.lat, "lon": place.lon, **extra})
        else:
            answer = _ask(action, {"query": candidate, **extra})
            _check_lookup(answer, query)
            if answer.get("place") is None:
                asked += _hosts(answer)
                continue
            place = _place(answer["place"])
        return place, answer, asked + _hosts(answer)
    raise AlertsError(
        f"I could not find a place called '{_cap(query, 60)}'. Check the spelling, or "
        "add the country, as in 'Paris, France'."
    )


def _alert(value: Any) -> _Alert:
    item = _record(value, "alert")
    return _Alert(
        _plain(item.get("event"), 60) or "Alert",
        _plain(item.get("severity"), 20) or "unknown",
        _plain(item.get("headline"), 110),
        _plain(item.get("area"), 40),
        _plain(item.get("source"), 60),
        _moment(item.get("effective")),
        _moment(item.get("expires")),
    )


def _sweep(answer: Dict[str, Any]) -> _Sweep:
    errors = (_plain(item, 200) for item in _list(answer.get("errors"), "errors"))
    return _Sweep(
        _count(answer, "days", least=1),
        tuple(_alert(item) for item in _list(answer.get("alerts"), "alerts")),
        tuple(error for error in errors if error),
        _count(answer, "feeds"),
    )


# --- Replies -----------------------------------------------------------------


def _footer(hosts: Sequence[str], now: datetime) -> List[str]:
    asked = list(dict.fromkeys(hosts))
    line = f"Asked through {PROJECT} at {_stamp(now)}"
    return ["", f"{line}: {_join(asked)}." if asked else f"{line}.", SAFETY_NOTE, CREDIT]


def _other_scale(value: float, unit: str) -> str:
    """`` (54°F)`` beside a reading in °C, and the reverse; nothing for other units."""

    if unit == "°C":
        return f" ({_round(value * 9 / 5 + 32)}°F)"
    if unit == "°F":
        return f" ({_round((value - 32) * 5 / 9)}°C)"
    return ""


def _speed(value: float, unit: str) -> str:
    if unit == "km/h":
        return f"{_round(value)} km/h ({_round(value / _KMH_PER_MPH)} mph)"
    if unit in ("mp/h", "mph"):
        return f"{_round(value)} mph ({_round(value * _KMH_PER_MPH)} km/h)"
    return f"{_round(value)} {unit}".rstrip()


def _weather_lines(answer: Dict[str, Any], place: _Place) -> List[str]:
    reading = _record(answer.get("weather"), "forecast")
    temperature, feels, high, low, humidity, rain, wind = (
        _number(reading, key)
        for key in ("temperature", "feelsLike", "high", "low", "humidity", "precipitation", "windSpeed")
    )
    if all(value is None for value in (temperature, feels, humidity, rain, wind)):
        raise AlertsError(f"No current weather came through for {place.where}; please try again later.")
    units = _record(reading.get("units"), "units")
    shown = _record(answer.get("shown"), "temperatures")
    degrees = _plain(units.get("temperature"), 8)

    def degrees_text(key: str, value: float) -> str:
        text = _plain(shown.get(key), 16)
        if not text:
            raise _unusable("temperatures")
        return text + _other_scale(value, degrees)

    lines = []
    current = [_plain(reading.get("label"), 60)]
    if temperature is not None:
        current.append(degrees_text("temperature", temperature))
    if feels is not None:
        current.append(f"feels like {degrees_text('feelsLike', feels)}")
    if any(current):
        lines.append(f"- Now: {', '.join(part for part in current if part)}.")
    today = []
    if high is not None:
        today.append(f"high {degrees_text('high', high)}")
    if low is not None:
        today.append(f"low {degrees_text('low', low)}")
    if today:
        lines.append(f"- Today: {', '.join(today)}.")
    details = []
    if wind is not None:
        details.append(f"wind {_speed(wind, _plain(units.get('wind'), 8))}")
    if humidity is not None:
        details.append(f"humidity {_round(humidity)}%")
    if rain is not None:
        rain_unit = _plain(units.get("precipitation"), 8)
        details.append(f"recent precipitation {_amount(rain)} {rain_unit}".rstrip())
    if details:
        text = ", ".join(details)
        lines.append(f"- {text[0].upper()}{text[1:]}.")
    if answer.get("rough") is True:
        lines.append(f"- {PROJECT} rates the weather now as rough.")
    observed = _local_time(reading.get("observedAt"))
    if observed:
        lines.append(f"- As of {observed}.")
    return lines


def weather(place: str, *, now: Optional[datetime] = None) -> str:
    """The current weather and today's range at ``place``, read through 5-Mins.

    Raises :class:`AlertsError` when the place or its forecast cannot be found.
    """

    when = _utc_now(now)
    found, answer, hosts = _at_place(place, "weather", {})
    if answer.get("error"):
        raise AlertsError(
            f"I couldn't get the weather for {found.where} just now: {_reason(answer['error'])}."
        )
    lines = [f"Weather {'in' if found.label else 'at'} {found.where}:"]
    lines += _weather_lines(answer, found)
    return "\n".join(lines + _footer(hosts, when))


def _alert_lines(alert: _Alert, now: datetime, with_area: bool = True) -> List[str]:
    detail = alert.headline
    if with_area and alert.area and _fold(alert.area) not in _fold(detail):
        detail = f"{detail} ({alert.area})" if detail else alert.area
    source = f" — {alert.source}" if alert.source else ""
    return [
        f"- {alert.event} (severity: {alert.severity}), "
        f"{_period(alert.effective, alert.expires, now)}",
        f"  {detail or alert.event}{source}",
    ]


def _listing(
    sweep: _Sweep, now: datetime, heading: str, empty: str, limit: int, with_area: bool = True
) -> List[str]:
    if not sweep.alerts:
        return [empty]
    lines = [heading]
    for alert in sweep.alerts[:limit]:
        lines += _alert_lines(alert, now, with_area)
    if len(sweep.alerts) > limit:
        lines.append(f"Showing the first {limit} of {len(sweep.alerts)}.")
    return lines


def _unanswered(subject: str, sweep: _Sweep) -> List[str]:
    return [
        f"I can't tell whether there are {subject}, because none of the feeds answered:"
    ] + [f"- {error}" for error in sweep.errors]


def _missing(sweep: _Sweep) -> List[str]:
    if not sweep.errors:
        return []
    return ["", "Some feeds did not answer, so this list may be incomplete:"] + [
        f"- {error}" for error in sweep.errors
    ]


def hazards(place: str, *, now: Optional[datetime] = None) -> str:
    """The hazard alerts 5-Mins finds near ``place``, most severe first.

    A feed that fails is listed at the end instead of hiding the others'
    alerts. Raises :class:`AlertsError` when the place cannot be found.
    """

    when = _utc_now(now)
    found, answer, hosts = _at_place(place, "hazards", {"now": when.isoformat(timespec="milliseconds")})
    sweep = _sweep(answer)
    where = found.where
    if sweep.none_answered:
        return "\n".join(_unanswered(f"hazard alerts near {where}", sweep) + _footer(hosts, when))
    lines = _listing(
        sweep,
        when,
        f"Hazard alerts near {where} from the last {_days(sweep.days)}, most severe first:",
        f"No hazard alerts near {where} from the last {_days(sweep.days)}.",
        MAX_ALERTS,
    )
    worldwide = _count(answer, "worldwide")
    if worldwide:
        one = worldwide == 1
        lines.append(
            f"There {'is' if one else 'are'} also {worldwide} worldwide alert{'' if one else 's'}, "
            f"such as space weather; ask for 'space weather' to see {'it' if one else 'them'}."
        )
    return "\n".join(lines + _missing(sweep) + _footer(hosts, when))


def space_weather(*, now: Optional[datetime] = None) -> str:
    """Space weather and the other worldwide alerts 5-Mins finds, most severe first.

    5-Mins finds these along with any place's alerts, so all of its feeds are
    asked.
    """

    when = _utc_now(now)
    answer = _ask("space_weather", {"now": when.isoformat(timespec="milliseconds")})
    sweep = _sweep(answer)
    hosts = _hosts(answer)
    if sweep.none_answered:
        return "\n".join(_unanswered("space weather alerts", sweep) + _footer(hosts, when))
    lines = _listing(
        sweep,
        when,
        f"Space weather and other worldwide alerts from the last {_days(sweep.days)}, "
        "most severe first:",
        f"No space weather or other worldwide alerts from the last {_days(sweep.days)}.",
        MAX_SPACE_ALERTS,
        with_area=False,
    )
    return "\n".join(lines + _missing(sweep) + _footer(hosts, when))


def usage() -> str:
    """How to ask for live weather and hazard alerts."""

    return "\n".join(
        [
            f"I can read live weather and hazard alerts through {PROJECT}, which checks free "
            "public feeds:",
            "- 'weather in Paris' for the current conditions and today's range",
            "- 'hazards near Manila' or 'any earthquakes near Lima' for recent alerts nearby",
            "- 'space weather' for space weather and other worldwide alerts",
            "Name a city, add its region or country ('Paris, Texas'), or give coordinates "
            "('48.85, 2.35').",
            "These go online, so web search must be on: start Jarvis with "
            "'--web-search manual' or '--web-search auto'.",
            "",
            SAFETY_NOTE,
            CREDIT,
        ]
    )
