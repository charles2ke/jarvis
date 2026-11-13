"""The current time in a city, country or IANA time zone.

Places resolve through the offline atlas: a major city first, then a country
(which keeps its capital's time), then a capital city. ``UTC``, ``GMT`` and
IANA names such as ``Asia/Tokyo`` work too. Daylight saving time comes from
the :mod:`zoneinfo` database; on systems without one the atlas's standard
offset is used and the reply says that daylight saving time was not applied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Dict, Optional, Tuple

from jarvis.atlas import (
    display_name,
    find_by_capital,
    find_city,
    find_country,
    timezone_for_country,
)
from jarvis.dates import MONTH_NAMES, WEEKDAY_NAMES

try:
    from zoneinfo import ZoneInfo, available_timezones
except ImportError:  # pragma: no cover - zoneinfo ships with Python 3.9+
    ZoneInfo = None  # type: ignore[assignment,misc]
    available_timezones = None  # type: ignore[assignment]

__all__ = [
    "CLOCK_HELP",
    "ClockError",
    "Place",
    "describe_difference",
    "describe_time",
    "find_place",
]

CLOCK_HELP = (
    "Ask me for the time in a country, a capital, a major city or a time zone, "
    "for example 'what time is it in Tokyo?' or 'current time in New York'."
)


class ClockError(ValueError):
    """Raised when a place or its time zone cannot be found."""


@dataclass(frozen=True)
class Place:
    """A place and the IANA time zone it keeps."""

    label: str
    zone: str
    standard_offset: str = ""
    note: str = ""
    is_zone: bool = False


_FILLER = re.compile(
    r"(?:[\s,]+(?:right\s+now|now|at\s+the\s+moment|currently|today|please|jarvis))+$",
    re.IGNORECASE,
)
_UTC_NAMES = {
    "utc": "UTC",
    "gmt": "GMT",
    "zulu": "UTC",
    "zulu time": "UTC",
    "coordinated universal time": "UTC",
    "universal time": "UTC",
    "greenwich mean time": "GMT",
    "greenwich": "GMT",
}
_OFFSET = re.compile(r"^UTC(?P<sign>[+-])(?P<hours>\d{2}):(?P<minutes>\d{2})$")
# Atlas notes that say a country keeps more than one civil time.
_MULTI_ZONE = re.compile(r"\b(?:spans|mainland|more time zones)\b", re.IGNORECASE)


def _clean(text: str) -> str:
    place = (text or "").strip().strip(" \t.,;:!?\"'")
    place = _FILLER.sub("", place)
    place = re.sub(r"^(?:the\s+)?(?:city\s+of\s+)?", "", place, flags=re.IGNORECASE)
    return place.strip(" \t.,;:!?\"'")


@lru_cache(maxsize=1)
def _zone_names() -> Dict[str, str]:
    if available_timezones is None:  # pragma: no cover - see import above
        return {}
    try:
        return {name.lower(): name for name in available_timezones()}
    except OSError:  # pragma: no cover - unreadable time zone database
        return {}


def find_place(text: str) -> Optional[Place]:
    """Return the place ``text`` names, or ``None`` when it is unknown."""

    name = _clean(text)
    if not name:
        return None
    key = name.lower()
    if key in _UTC_NAMES:
        return Place(_UTC_NAMES[key], "UTC", "UTC+00:00", is_zone=True)

    city = find_city(name)
    if city is not None:
        return Place(city.name, city.timezone, city.utc_offset)

    country = find_country(name)
    if country is not None:
        zone = timezone_for_country(country)
        if zone is None:
            return None
        if _MULTI_ZONE.search(zone.note):
            label = f"{country.capital}, the capital of {display_name(country)},"
            return Place(label, zone.zone, zone.utc_offset, zone.note)
        return Place(display_name(country), zone.zone, zone.utc_offset, zone.note)

    country = find_by_capital(name)
    if country is not None:
        zone = timezone_for_country(country)
        if zone is not None:
            return Place(country.capital, zone.zone, zone.utc_offset)
        return None

    if "/" in name:
        zone_name = _zone_names().get(re.sub(r"\s+", "_", key))
        if zone_name is not None:
            return Place(zone_name, zone_name, is_zone=True)
    return None


def _fixed_offset(text: str) -> Optional[timedelta]:
    found = _OFFSET.match(text or "")
    if found is None:
        return None
    offset = timedelta(hours=int(found.group("hours")), minutes=int(found.group("minutes")))
    return -offset if found.group("sign") == "-" else offset


def _local_time(place: Place, instant: datetime) -> Tuple[datetime, bool]:
    """Return the time at ``place`` and whether daylight saving is accounted for."""

    if ZoneInfo is not None:
        try:
            return instant.astimezone(ZoneInfo(place.zone)), True
        except (KeyError, ValueError, OSError):
            pass  # No time zone database: use the standard offset below.
    offset = _fixed_offset(place.standard_offset)
    if offset is None:
        raise ClockError(
            f"I need time zone data to tell the time in {place.label}, and none "
            "is installed. On Windows, 'pip install tzdata' adds it."
        )
    return instant.astimezone(timezone(offset)), False


def _format_offset(offset: Optional[timedelta]) -> str:
    minutes = int((offset or timedelta()).total_seconds() // 60)
    sign = "-" if minutes < 0 else "+"
    hours, minutes = divmod(abs(minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _gap(difference: timedelta) -> str:
    """Return '9 hours' or '5 hours and 30 minutes' for a non-zero difference."""

    hours, rest = divmod(abs(int(difference.total_seconds() // 60)), 60)
    parts = [_plural(hours, "hour")] if hours else []
    if rest:
        parts.append(_plural(rest, "minute"))
    return " and ".join(parts)


def _relative(difference: timedelta) -> str:
    if difference.total_seconds() // 60 == 0:
        return "That is the same as your local time."
    direction = "ahead of" if difference > timedelta() else "behind"
    return f"That is {_gap(difference)} {direction} you."


def _require_place(text: str) -> Place:
    place = find_place(text)
    if place is None:
        name = _clean(text) or (text or "").strip()
        raise ClockError(f"I do not know the time zone of '{name}'. {CLOCK_HELP}")
    return place


def _clock_and_day(local: datetime) -> Tuple[str, str]:
    clock = f"{local.hour:02d}:{local.minute:02d}"
    return clock, f"{WEEKDAY_NAMES[local.weekday()]}, {local.day} {MONTH_NAMES[local.month]}"


def describe_difference(first: str, second: str, now: datetime) -> str:
    """Return how far ahead of or behind the place ``second`` names ``first`` is."""

    places = [_require_place(first), _require_place(second)]
    instant = now if now.tzinfo is not None else now.astimezone()
    times = [_local_time(place, instant) for place in places]
    labels = [place.label.rstrip(",") for place in places]
    (one, one_exact), (two, two_exact) = times
    difference = one.utcoffset() - two.utcoffset()
    (clock_one, day_one), (clock_two, day_two) = _clock_and_day(one), _clock_and_day(two)
    if difference.total_seconds() // 60 == 0:
        reply = (
            f"{labels[0]} and {labels[1]} keep the same time: it is {clock_one} "
            f"on {day_one} in both."
        )
    else:
        direction = "ahead of" if difference > timedelta() else "behind"
        reply = (
            f"{labels[0]} is {_gap(difference)} {direction} {labels[1]}. It is "
            f"{clock_one} on {day_one} in {labels[0]} and {clock_two} on {day_two} "
            f"in {labels[1]}."
        )
    if not (one_exact and two_exact):
        reply += (
            " I could not load time zone data, so daylight saving time is not applied."
        )
    return reply


def describe_time(text: str, now: datetime) -> str:
    """Return the current time at the place ``text`` names.

    ``now`` is the current moment; a naive value is read as the computer's
    local time, which is also what 'ahead of you' compares against.
    """

    place = _require_place(text)
    instant = now if now.tzinfo is not None else now.astimezone()
    local, exact = _local_time(place, instant)
    clock, day = _clock_and_day(local)
    offset = _format_offset(local.utcoffset())

    if not exact:
        reply = (
            f"In {place.label} it is about {clock} on {day} ({offset}, standard "
            "time: I could not load time zone data, so daylight saving time is "
            "not applied)."
        )
    else:
        details = [] if place.is_zone else [place.zone]
        if place.zone != "UTC":
            details.append(offset)
        if local.dst():
            details.append("daylight saving time")
        detail = f" ({', '.join(details)})" if details else ""
        if place.is_zone:
            reply = f"It is {clock} on {day} in {place.label}{detail}."
        else:
            reply = f"In {place.label} it is {clock} on {day}{detail}."
    parts = [reply, _relative(local.utcoffset() - instant.utcoffset())]
    if place.note:
        parts.append(place.note)
    return " ".join(parts)
