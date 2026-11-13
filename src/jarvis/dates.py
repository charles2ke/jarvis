"""Offline date parsing and arithmetic for the date skills.

Everything here works on plain :class:`datetime.date` values and English month,
weekday and holiday names, so answers never depend on the system locale or the
network. :func:`parse_date` reads the dates people type (``25 December 2026``,
``Dec 25th``, ``2027-01-01``, ``christmas``, ``next friday``, ``tomorrow``) and
the ``countdown``, ``time_since``, ``days_between``, ``weekday_of``,
``shifted``, ``age``, ``leap_year``, ``month_length`` and ``year_length``
helpers turn them into replies.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Dict, Optional, Tuple

__all__ = [
    "DATE_HELP",
    "DATE_HINT",
    "DATE_WORD_HINT",
    "DateError",
    "HOLIDAYS",
    "MONTH_NAMES",
    "MONTH_PATTERN",
    "NamedDate",
    "WEEKDAY_NAMES",
    "age",
    "countdown",
    "days_between",
    "format_date",
    "leap_year",
    "month_length",
    "parse_date",
    "shift",
    "shifted",
    "time_since",
    "weekday_of",
    "year_length",
]

MONTH_NAMES: Tuple[str, ...] = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

WEEKDAY_NAMES: Tuple[str, ...] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

DATE_HELP = (
    "I can count the days until or since a date, tell you the weekday of any "
    "date, add or subtract days, weeks, months or years, work out ages and "
    "check leap years. Try 'how many days until Christmas', 'what day of the "
    "week is 1 January 2027' or 'what is the date in 10 days'."
)

#: Month names and abbreviations, for skill patterns.
MONTH_PATTERN = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_WEEKDAY_PATTERN = (
    r"mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?"
    r"|fri(?:day)?|sat(?:urday)?|sun(?:day)?"
)

#: Words that only appear in a date. Skill patterns use this as a lookahead so
#: that, for example, "how long to boil an egg" is not read as a date question.
DATE_WORD_HINT = (
    r"\b(?:" + MONTH_PATTERN + r"|" + _WEEKDAY_PATTERN
    + r"|today|tomorrow|yesterday|christmas|xmas|new\s+year(?:'?s)?|halloween"
    r"|valentine(?:'?s)?|(?:st\.?|saint)\s+patrick(?:'?s)?|april\s+fool(?:'?s)?"
    r"|boxing\s+day|end\s+of\s+(?:the\s+|this\s+)?(?:year|month))(?![a-z])"
)

#: Like :data:`DATE_WORD_HINT`, but a digit counts too.
DATE_HINT = r"(?:\d|" + DATE_WORD_HINT + r")"


class DateError(ValueError):
    """Raised when a date cannot be read or falls outside the calendar."""


@dataclass(frozen=True)
class Holiday:
    """A holiday that falls on the same day every year."""

    name: str
    month: int
    day: int
    aliases: Tuple[str, ...] = ()


HOLIDAYS: Tuple[Holiday, ...] = (
    Holiday("New Year's Day", 1, 1, ("new year", "new years", "new year day")),
    Holiday("Valentine's Day", 2, 14, ("valentines", "valentine")),
    Holiday(
        "St Patrick's Day",
        3,
        17,
        ("st patricks", "saint patricks day", "saint patricks", "st patrick day"),
    ),
    Holiday("April Fools' Day", 4, 1, ("april fools", "april fool", "april fool day")),
    Holiday("Halloween", 10, 31),
    Holiday("Christmas Eve", 12, 24),
    Holiday("Christmas", 12, 25, ("christmas day", "xmas", "xmas day")),
    Holiday("Boxing Day", 12, 26),
    Holiday("New Year's Eve", 12, 31, ("new years eve", "new year eve")),
)


@dataclass(frozen=True)
class NamedDate:
    """A parsed date, with the name it was given when that reads better."""

    value: date
    name: Optional[str] = None
    #: False when the year was inferred, as for "25 December" or "Christmas".
    explicit_year: bool = True
    #: True for dates counted from today, such as "tomorrow" or "next Friday".
    relative: bool = False

    def describe(self) -> str:
        """Return ``Christmas (Friday, 25 December 2026)`` or just the date."""

        if self.name:
            return f"{self.name} ({format_date(self.value)})"
        return format_date(self.value)


def _key(text: str) -> str:
    """Return a lowercase, apostrophe-free key for ``text``."""

    lowered = (text or "").lower().replace("\u2019", "'").replace("'", "")
    lowered = re.sub(r"\.(?=\s)", "", lowered)  # "St. Patrick", "Dec. 25"
    lowered = re.sub(r"\s+", " ", lowered).strip(" \t.,!?;:\"")
    lowered = re.sub(r"^(?:on|the)\s+", "", lowered)
    return re.sub(r"^(?:on|the)\s+", "", lowered)


def _build_months() -> Dict[str, int]:
    months: Dict[str, int] = {}
    for index, name in enumerate(MONTH_NAMES[1:], start=1):
        months[name.lower()] = index
        months[name[:3].lower()] = index
    months["sept"] = 9
    return months


def _build_weekdays() -> Dict[str, int]:
    weekdays: Dict[str, int] = {}
    for index, name in enumerate(WEEKDAY_NAMES):
        weekdays[name.lower()] = index
        weekdays[name[:3].lower()] = index
    weekdays.update({"tues": 1, "weds": 2, "thur": 3, "thurs": 3})
    return weekdays


def _build_holidays() -> Dict[str, Holiday]:
    holidays: Dict[str, Holiday] = {}
    for holiday in HOLIDAYS:
        for alias in (holiday.name, *holiday.aliases):
            holidays[_key(alias)] = holiday
    return holidays


_MONTHS = _build_months()
_WEEKDAYS = _build_weekdays()
_HOLIDAYS = _build_holidays()

_UNITS = (
    "zero first second third fourth fifth sixth seventh eighth ninth tenth eleventh "
    "twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth"
).split()
_ORDINAL_WORDS: Dict[str, int] = {word: value for value, word in enumerate(_UNITS) if value}
_ORDINAL_WORDS.update({"twentieth": 20, "thirtieth": 30})
for _tens, _value in (("twenty", 20), ("thirty", 30)):
    for _unit in range(1, 10):
        _ORDINAL_WORDS[f"{_tens}-{_UNITS[_unit]}"] = _value + _unit
        _ORDINAL_WORDS[f"{_tens} {_UNITS[_unit]}"] = _value + _unit

_DAY = (
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?|(?P<day_word>"
    + "|".join(sorted((re.escape(word) for word in _ORDINAL_WORDS), key=len, reverse=True))
    + r")"
)
_MONTH = r"(?P<month>" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?"
_YEAR = r"(?:,?\s+(?P<year>\d{4}))?"

_DAY_MONTH = re.compile(rf"^(?:{_DAY})\s+(?:of\s+)?{_MONTH}{_YEAR}$")
_MONTH_DAY = re.compile(rf"^{_MONTH}\s+(?:the\s+)?(?:{_DAY}){_YEAR}$")
_ISO = re.compile(r"^(?P<year>\d{4})[-/.](?P<month>\d{1,2})[-/.](?P<day>\d{1,2})$")
_WEEKDAY = re.compile(
    r"^(?:(?P<which>next|this|last|coming)\s+)?(?P<weekday>"
    + "|".join(sorted(_WEEKDAYS, key=len, reverse=True))
    + r")$"
)
_RELATIVE_YEAR = re.compile(r"^(?P<rest>.+?)\s+(?P<which>this|next|last)\s+year$")
_HOLIDAY_YEAR = re.compile(r"^(?P<name>.+?)(?:,?\s+(?P<year>\d{4}))?$")
_END_OF = re.compile(r"^end\s+of\s+(?:the\s+|this\s+)?(?P<period>year|month)$")

_RELATIVE_DAYS = {
    "today": (0, "today"),
    "tomorrow": (1, "tomorrow"),
    "yesterday": (-1, "yesterday"),
    "day after tomorrow": (2, "the day after tomorrow"),
    "day before yesterday": (-2, "the day before yesterday"),
}
_RELATIVE_NAMES = frozenset(name for _, name in _RELATIVE_DAYS.values())


def format_date(value: date) -> str:
    """Return ``Friday, 25 December 2026`` for ``value``, in English."""

    return (
        f"{WEEKDAY_NAMES[value.weekday()]}, {value.day} "
        f"{MONTH_NAMES[value.month]} {value.year}"
    )


def _check_year(year: int) -> int:
    if not 1 <= year <= 9999:
        raise DateError("I can only work with years from 1 to 9999.")
    return year


def _make_date(year: int, month: int, day: int) -> date:
    _check_year(year)
    if not 1 <= month <= 12:
        raise DateError(f"There is no month {month}; months run from 1 to 12.")
    length = calendar.monthrange(year, month)[1]
    if not 1 <= day <= length:
        raise DateError(f"{MONTH_NAMES[month]} {year} has only {length} days.")
    return date(year, month, day)


def _occurrence(month: int, day: int, today: date, prefer: str) -> date:
    """Return the next (or, for ``prefer='past'``, the latest) ``day month``."""

    if day > (29 if month == 2 else calendar.monthrange(2001, month)[1]):
        raise DateError(
            f"{MONTH_NAMES[month]} never has {day} days."
            if day <= 31
            else f"There is no day {day} in any month."
        )
    step = -1 if prefer == "past" else 1
    year = today.year
    for _ in range(9):  # 29 February comes round at least every eight years.
        if 1 <= year <= 9999 and day <= calendar.monthrange(year, month)[1]:
            candidate = date(year, month, day)
            if (candidate <= today) if prefer == "past" else (candidate >= today):
                return candidate
        year += step
    raise DateError("That date is outside the calendar I can work with.")


def parse_date(text: str, today: date, prefer: str = "future") -> Optional[NamedDate]:
    """Return the date ``text`` describes, or ``None`` when it is not a date.

    Dates without a year resolve to the next occurrence on or after ``today``,
    or with ``prefer='past'`` the latest one on or before it. Raises
    :class:`DateError` for impossible dates such as ``31 February 2027``.
    """

    key = _key(text)
    if not key:
        return None

    end = _END_OF.match(key)
    if end:
        if end.group("period") == "year":
            return NamedDate(date(today.year, 12, 31), "the end of the year", relative=True)
        last = calendar.monthrange(today.year, today.month)[1]
        return NamedDate(
            date(today.year, today.month, last), "the end of the month", relative=True
        )

    relative = _RELATIVE_YEAR.match(key)
    if relative and not relative.group("rest").isdigit():
        offset = {"this": 0, "next": 1, "last": -1}[relative.group("which")]
        found = parse_date(relative.group("rest"), today, prefer)
        if found is None:
            return None
        year = _check_year(today.year + offset)
        try:
            moved = found.value.replace(year=year)
        except ValueError as exc:
            raise DateError(f"{year} has no {found.value.day} February.") from exc
        return NamedDate(moved, found.name, explicit_year=True)

    if key in _RELATIVE_DAYS:
        days, name = _RELATIVE_DAYS[key]
        try:
            return NamedDate(today + timedelta(days=days), name, relative=True)
        except OverflowError as exc:
            raise DateError("That date is outside the calendar I can work with.") from exc

    weekday = _WEEKDAY.match(key)
    if weekday:
        target = _WEEKDAYS[weekday.group("weekday")]
        which = weekday.group("which")
        if which == "last" or (which is None and prefer == "past"):
            back = (today.weekday() - target) % 7
            if which == "last" and back == 0:
                back = 7
            return NamedDate(today - timedelta(days=back), relative=True)
        ahead = (target - today.weekday()) % 7
        if which in ("next", "coming") and ahead == 0:
            ahead = 7
        return NamedDate(today + timedelta(days=ahead), relative=True)

    iso = _ISO.match(key)
    if iso:
        return NamedDate(
            _make_date(int(iso.group("year")), int(iso.group("month")), int(iso.group("day")))
        )

    for pattern in (_DAY_MONTH, _MONTH_DAY):
        found = pattern.match(key)
        if found:
            day_text = found.group("day")
            day = int(day_text) if day_text else _ORDINAL_WORDS[found.group("day_word")]
            month = _MONTHS[found.group("month")]
            year = found.group("year")
            if year:
                return NamedDate(_make_date(int(year), month, day))
            return NamedDate(_occurrence(month, day, today, prefer), explicit_year=False)

    holiday_match = _HOLIDAY_YEAR.match(key)
    if holiday_match and holiday_match.group("name") in _HOLIDAYS:
        holiday = _HOLIDAYS[holiday_match.group("name")]
        year = holiday_match.group("year")
        if year:
            return NamedDate(_make_date(int(year), holiday.month, holiday.day), holiday.name)
        return NamedDate(
            _occurrence(holiday.month, holiday.day, today, prefer),
            holiday.name,
            explicit_year=False,
        )
    return None


def _require(text: str, today: date, prefer: str = "future") -> NamedDate:
    found = parse_date(text, today, prefer)
    if found is None:
        raise DateError(
            f"I could not work out which date '{text.strip()}' is. Try a date such "
            "as '25 December 2026', 'Dec 25', '2027-01-01', 'Christmas' or 'next Friday'."
        )
    return found


def shift(start: date, amount: int, unit: str) -> date:
    """Return ``start`` moved by ``amount`` days, weeks, fortnights, months or years.

    Months and years keep the day of the month where they can and otherwise
    use the last day of the month, so 31 January plus one month is 28 or 29
    February.
    """

    name = unit.lower().rstrip("s")
    try:
        if name in ("day", "week", "fortnight"):
            days = amount * {"day": 1, "week": 7, "fortnight": 14}[name]
            return start + timedelta(days=days)
        if name in ("month", "year"):
            months = amount * (12 if name == "year" else 1)
            index = start.year * 12 + start.month - 1 + months
            year, month = divmod(index, 12)
            _check_year(year)
            length = calendar.monthrange(year, month + 1)[1]
            return date(year, month + 1, min(start.day, length))
    except (OverflowError, DateError) as exc:
        raise DateError("That date is outside the calendar I can work with.") from exc
    raise DateError(f"I do not know how to count in '{unit}'.")


def _plural(count: int, word: str) -> str:
    return f"{count:,} {word}" if count == 1 else f"{count:,} {word}s"


def _anniversary(start: date, year: int) -> date:
    """Return ``start``'s month and day in ``year``, using 28 February for 29 February."""

    return date(year, start.month, min(start.day, calendar.monthrange(year, start.month)[1]))


def _whole_years(start: date, end: date) -> int:
    years = end.year - start.year
    if (end.month, end.day) < (start.month, start.day):
        years -= 1
    return years


def _span(start: date, end: date) -> str:
    """Describe the time from ``start`` to a later ``end``, in days and more."""

    days = (end - start).days
    text = _plural(days, "day")
    if days >= 365:
        years = _whole_years(start, end)
        rest = (end - _anniversary(start, start.year + years)).days
        detail = _plural(years, "year") + (f" and {_plural(rest, 'day')}" if rest else "")
        return f"{text} ({detail})"
    if days >= 14:
        weeks, rest = divmod(days, 7)
        detail = _plural(weeks, "week") + (f" and {_plural(rest, 'day')}" if rest else "")
        return f"{text} ({detail})"
    return text


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def countdown(text: str, today: date) -> str:
    """Reply to 'how many days until ``text``'."""

    target = _require(text, today)
    days = (target.value - today).days
    if target.name in _RELATIVE_NAMES and days in (0, 1):
        return f"{_capital(target.name)} is {format_date(target.value)}."
    if days == 0:
        return f"{_capital(target.describe())} is today."
    if days == 1:
        return f"{_capital(target.describe())} is tomorrow."
    if days < 0:
        return f"{_capital(target.describe())} was {_span(target.value, today)} ago."
    verb = "is" if days == 1 else "are"
    return f"There {verb} {_span(today, target.value)} until {target.describe()}."


def time_since(text: str, today: date) -> str:
    """Reply to 'how long has it been since ``text``'."""

    target = _require(text, today, prefer="past")
    if target.value >= today:
        return countdown(text, today)
    return f"It has been {_span(target.value, today)} since {target.describe()}."


def _in_year(found: NamedDate, year: int) -> Optional[NamedDate]:
    """Return ``found`` moved to ``year``, or ``None`` if that year lacks the day."""

    if not 1 <= year <= 9999:
        return None
    try:
        return replace(found, value=found.value.replace(year=year), explicit_year=True)
    except ValueError:  # 29 February outside a leap year
        return None


def _align_years(start: NamedDate, end: NamedDate) -> Tuple[NamedDate, NamedDate]:
    """Read dates without a year in the same year as the other date.

    "1 Jan to 31 Dec" is one year rather than a single day backwards, and
    "1 March 2026 to 1 June" stays in 2026.
    """

    if not start.explicit_year and not end.explicit_year:
        for year in (start.value.year, start.value.year + 1):
            moved = _in_year(end, year)
            if moved is not None and moved.value >= start.value:
                return start, moved
        return start, end
    if not end.explicit_year and not start.relative:
        return start, _in_year(end, start.value.year) or end
    if not start.explicit_year and not end.relative:
        return _in_year(start, end.value.year) or start, end
    return start, end


def days_between(first: str, second: str, today: date) -> str:
    """Reply to 'how many days between ``first`` and ``second``'."""

    start, end = _align_years(_require(first, today), _require(second, today))
    if end.value < start.value:
        start, end = end, start
    if start.value == end.value:
        return f"Those are the same day: {start.describe()}."
    verb = "is" if (end.value - start.value).days == 1 else "are"
    return (
        f"There {verb} {_span(start.value, end.value)} between {start.describe()} "
        f"and {end.describe()}."
    )


def weekday_of(text: str, today: date, past: bool = False) -> str:
    """Reply to 'what day of the week is ``text``'."""

    target = _require(text, today, prefer="past" if past else "future")
    value = target.value
    weekday = WEEKDAY_NAMES[value.weekday()]
    verb = "was" if value < today else "is"
    if target.name in _RELATIVE_NAMES:
        return f"{_capital(target.name)} {verb} {format_date(value)}."
    day_month_year = f"{value.day} {MONTH_NAMES[value.month]} {value.year}"
    if target.name:
        return f"{_capital(target.name)} ({day_month_year}) {verb} on a {weekday}."
    return f"{day_month_year} {verb} a {weekday}."


def shifted(
    amount: str,
    unit: str,
    today: date,
    *,
    backwards: bool = False,
    base: Optional[str] = None,
) -> str:
    """Reply to 'what is the date ``amount`` ``unit`` from now', ago or after ``base``."""

    count = 1 if amount.lower() in ("a", "an") else int(amount)
    if count > 1_000_000:
        raise DateError("That date is outside the calendar I can work with.")
    name = unit.lower().rstrip("s")
    words = _plural(count, name)
    start = _require(base, today) if base else None
    origin = start.value if start else today
    result = shift(origin, -count if backwards else count, name)
    if start is not None:
        relation = "before" if backwards else "after"
        verb = "was" if result < today else "is"
        return f"{_capital(words)} {relation} {start.describe()} {verb} {format_date(result)}."
    if backwards:
        return f"{_capital(words)} ago was {format_date(result)}."
    return f"{_capital(words)} from today is {format_date(result)}."


def age(text: str, today: date, you: bool = False) -> str:
    """Reply to 'how old is someone born on ``text``', or to 'how old am I' with ``you``."""

    cleaned = _key(text)
    if re.fullmatch(r"\d{4}", cleaned):
        year = _check_year(int(cleaned))
        older = today.year - year
        if older < 0:
            raise DateError(f"{year} is still to come.")
        lead = f"If you were born in {year}, you are" if you else f"Someone born in {year} is"
        if older == 0:
            return f"{lead} less than a year old."
        whose = "your" if you else "their"
        return (
            f"{lead} {older} if {whose} birthday has already come this year, "
            f"or {older - 1} if it is still to come."
        )
    birth = _require(text, today, prefer="past")
    if not birth.explicit_year:
        raise DateError(
            "Tell me the year as well, for example 'how old is someone born on "
            "3 March 1990?'."
        )
    if birth.value > today:
        raise DateError(f"{format_date(birth.value)} is still to come.")
    born = format_date(birth.value)
    if birth.value == today:
        return f"{born} is today, so {'you are' if you else 'they are'} a newborn."
    years = _whole_years(birth.value, today)
    birthday = _anniversary(birth.value, today.year)
    if birthday == today:
        if you:
            return f"You turn {years} today. Happy birthday!"
        return f"Someone born on {born} turns {years} today. Happy birthday!"
    if birthday < today:
        birthday = _anniversary(birth.value, today.year + 1)
    upcoming = f"birthday is in {_span(today, birthday)}, on {format_date(birthday)}."
    if you:
        return (
            f"You were born on {born}, so you are {_plural(years, 'year')} old. "
            f"Your next {upcoming}"
        )
    return f"Someone born on {born} is {_plural(years, 'year')} old. Their next {upcoming}"


def _next_leap_year(after: int) -> int:
    year = after + 1
    while not calendar.isleap(year):
        year += 1
    return year


def leap_year(year: Optional[str], today: date, next_one: bool = False) -> str:
    """Reply to 'is ``year`` a leap year' or 'when is the next leap year'."""

    if next_one:
        return f"The next leap year is {_next_leap_year(today.year)}."
    value = _check_year(int(year)) if year else today.year
    if calendar.isleap(value):
        return f"Yes, {value} is a leap year, so February has 29 days."
    return (
        f"No, {value} is not a leap year, so February has 28 days. The next "
        f"leap year is {_next_leap_year(value)}."
    )


def month_length(month: str, year: Optional[str], today: date) -> str:
    """Reply to 'how many days are in ``month`` [``year``]'."""

    number = _MONTHS[_key(month).rstrip(".")]
    name = MONTH_NAMES[number]
    value = _check_year(int(year)) if year else today.year
    days = calendar.monthrange(value, number)[1]
    if year:
        return f"{name} {value} has {days} days."
    if number == 2:
        return (
            f"February has 28 days, or 29 in a leap year. February {value} has {days}."
        )
    return f"{name} has {days} days."


def year_length(year: str) -> str:
    """Reply to 'how many days are in ``year``'."""

    value = _check_year(int(year))
    days = 366 if calendar.isleap(value) else 365
    return f"{value} has {days} days."
