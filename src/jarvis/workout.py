"""The 7-day workout plan from the user's workout project, available offline.

workout (https://charles2ke.github.io/workout/, source at
https://github.com/charles2ke/workout) is the user's own "7-Day Longevity &
Strength Program". :data:`WEEK` is ``WORKOUT_DATA`` from its ``workout.js``
at commit 0c0d42575909 (19 September 2026), without the exercise ids and
illustrations. Replies show each exercise's stats with commas in place of the
original "•" separators.

:func:`plan` answers "what's my workout today?", "tomorrow's workout",
"Friday workout", "when is leg day?", "is today a rest day?" and "weekly
workout plan". It returns ``None`` when the text is not a question about the
plan — "work out what day it is", "what's a good workout for abs?", "I just
finished my workout", "what should I eat after my workout?" — so the caller can
fall back to something else. Single-day replies end with a short safety note, and
they say that the Zone 2 heart-rate target is the original author's own.

workout is MIT-licensed, and its notice covers the plan data here:

    MIT License

    Copyright (c) 2026 Charles Gomes

    Permission is hereby granted, free of charge, to any person obtaining a
    copy of this software and associated documentation files (the
    "Software"), to deal in the Software without restriction, including
    without limitation the rights to use, copy, modify, merge, publish,
    distribute, sublicense, and/or sell copies of the Software, and to permit
    persons to whom the Software is furnished to do so, subject to the
    following conditions:

    The above copyright notice and this permission notice shall be included
    in all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
    OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
    MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN
    NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
    DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
    OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE
    USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from jarvis.dates import WEEKDAY_NAMES

PROJECT = "workout"
SITE_URL = "https://charles2ke.github.io/workout/"
REPO_URL = "https://github.com/charles2ke/workout"
CREDIT = f"From {PROJECT}: {SITE_URL}"
PROGRAM = "7-Day Longevity & Strength Program"
SAFETY_NOTE = (
    "Warm up first, stop if you feel pain, dizziness or chest discomfort, and check "
    "with a doctor before starting a new exercise programme if you have a health "
    "condition."
)


@dataclass(frozen=True)
class Exercise:
    """One exercise; ``stats`` keeps the original "•" separators."""

    name: str
    stats: str
    notes: str
    difficulty: str
    rest_seconds: int
    rounds: int


@dataclass(frozen=True)
class Day:
    """One day of the plan."""

    id: str
    label: str
    title: str
    description: str
    estimated_minutes: int
    exercises: Tuple[Exercise, ...]

    @property
    def focus(self) -> str:
        """The title without its weekday, such as "Lower Body & Core"."""

        return self.title.partition(": ")[2] or self.title


# Monday first, as in the source, so ``WEEK[when.weekday()]`` is the day's
# workout, just like the source's DAY_IDS_BY_INDEX[date.getDay()].
WEEK: Tuple[Day, ...] = (
    Day(
        "mon",
        "Mon",
        "Monday: Upper Body Push & Pull",
        "Upper body strength and joint stability.",
        45,
        (
            Exercise(
                "Bench Press / Push-ups",
                "3 Sets • 8–12 Reps • 90s Rest",
                "Retract shoulder blades; elbows tucked at 45°.",
                "Moderate",
                90,
                3,
            ),
            Exercise(
                "Lat Pulldowns / Pull-ups",
                "3 Sets • 8–10 Reps • 90s Rest",
                "Drive with elbows down smoothly to upper chest.",
                "Moderate",
                90,
                3,
            ),
        ),
    ),
    Day(
        "tue",
        "Tue",
        "Tuesday: Lower Body & Core",
        "Leg power with spine protection.",
        40,
        (
            Exercise(
                "Goblet Squats",
                "3 Sets • 10–12 Reps • 90s Rest",
                "Upright chest, sit between hips, knees out.",
                "Moderate",
                90,
                3,
            ),
        ),
    ),
    Day(
        "wed",
        "Wed",
        "Wednesday: Active Recovery",
        "Aerobic base and joint mobility work.",
        30,
        (
            Exercise(
                "Zone 2 Cardio",
                "30 Mins • HR 105–120 BPM",
                "Brisk walk, light cycling, or light rowing.",
                "Easy",
                30,
                1,
            ),
        ),
    ),
    Day(
        "thu",
        "Thu",
        "Thursday: Upper Body Hypertrophy",
        "Posture strengthening and back alignment.",
        40,
        (
            Exercise(
                "Single-Arm DB Rows",
                "3 Sets • 10 Reps/side • 60s Rest",
                "Pull dumbbell to hip, keeping elbow close.",
                "Moderate",
                60,
                3,
            ),
        ),
    ),
    Day(
        "fri",
        "Fri",
        "Friday: Lower Body & Posterior Chain",
        "Glutes and hamstrings for joint support.",
        40,
        (
            Exercise(
                "Bulgarian Split Squats",
                "3 Sets • 8 Reps/leg • 90s Rest",
                "Keep front foot flat; controls hip stability.",
                "Hard",
                90,
                3,
            ),
        ),
    ),
    Day(
        "sat",
        "Sat",
        "Saturday: Full Body Conditioning",
        "Endurance circuit and core strength.",
        35,
        (
            Exercise(
                "Kettlebell Swings",
                "3 Rounds • 12–15 Reps",
                "Explode from the hips; power comes from glutes.",
                "Moderate",
                45,
                3,
            ),
        ),
    ),
    Day(
        "sun",
        "Sun",
        "Sunday: Rest & Recovery",
        "Full rest day for total muscle recovery.",
        20,
        (
            Exercise(
                "Foam Rolling & Walk",
                "15–20 Mins • Light Pressure",
                "Focus on upper back, quads, and calves.",
                "Easy",
                30,
                1,
            ),
        ),
    ),
)

DAYS: Tuple[str, ...] = tuple(day.title for day in WEEK)


# ---------------------------------------------------------------------------
# Understanding the question
# ---------------------------------------------------------------------------

_WORKOUT = r"work-?outs?"
# "work out" is also an everyday verb ("work out what day it is"), so it only
# counts after "I" or "we", or at the start, and not before a likely object.
_NOT_AN_OBJECT = (
    r"(?!\s+(?:what|how|which|why|whether|if|who|where|when|the|a|an|my|your|his|her"
    r"|their|our|this|that|these|those|it|its|\d))"
)
_CONTEXT_RE = re.compile(
    rf"\b{_WORKOUT}\b"
    rf"|(?:^|\b(?:i|we)(?:'ll|'m|'d|'re|'ve)?\s+(?:[a-z']+\s+){{0,3}}?)work(?:ing|ed)?\s+out\b"
    rf"{_NOT_AN_OBJECT}"
    r"|\btraining\s+(?:plan|session|schedule|day|program(?:me)?|routine|split)s?\b"
    r"|\bmy\s+training\b"
    r"|\b(?:exercise|fitness|gym)\s+(?:plan|routine|schedule|program(?:me)?|split|session|day)s?\b"
)
# Phrases that are about a workout plan on their own.
_SELF_CONTEXT_RE = re.compile(
    r"\b(?:legs?|arms?|rest|recovery)\s+days?\b"
    r"|\b(?:upper|lower)[- ]body\s+(?:days?|sessions?|work-?outs?|training)\b"
    r"|^(?:show|list)\s+(?:me\s+)?(?:the\s+|this\s+)?(?:whole\s+|full\s+)?week(?:'s)?"
    r"(?:\s+plan)?$"
)
# "exercise" or "gym" counts with a day: "what exercise today?", not "is the
# gym open on Sunday?".
_EXERCISE_RE = re.compile(r"\b(?:exercis(?:e|es|ing)|gym)\b")
_GYM_VISIT_RE = re.compile(
    r"\b(?:open|opens|opening|closed?|closes|closing|hours|membership|busy)\b"
)

_RELATIVE_DAYS: Tuple[Tuple["re.Pattern[str]", int, str], ...] = (
    (
        re.compile(rf"\b(?:today|tonight|this\s+(?:morning|afternoon|evening))\b"
                   rf"|\b{_WORKOUT}\s+of\s+the\s+day\b"),
        0,
        "today",
    ),
    (re.compile(r"\b(?:tomorrow|tmrw)\b"), 1, "tomorrow"),
    (re.compile(r"\byesterday\b"), -1, "yesterday"),
)
_WEEKDAY_RE = re.compile(
    r"\b(" + "|".join(name.lower() for name in WEEKDAY_NAMES) + r")s?\b"
)
_ABBREVIATIONS = {
    "mon": 0,
    "tue": 1,
    "tues": 1,
    "wed": 2,
    "weds": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}
_ABBREVIATION = "|".join(sorted(_ABBREVIATIONS, key=len, reverse=True))
# Abbreviations are only read next to "workout": "fri workout", "workout on sat".
_ABBREVIATION_RE = re.compile(
    rf"\b(?P<before>{_ABBREVIATION})(?:'s)?\s+{_WORKOUT}\b"
    rf"|\b{_WORKOUT}\s+(?:for|on)\s+(?P<after>{_ABBREVIATION})\b"
)
_IS_IT_RE = re.compile(r"\bis\s+it\b|\bit's\b")

_WEEK_RE = re.compile(
    r"\bweek(?:ly|'s)?\b|\b(?:7|seven)[- ]days?\b|\bplan\b|\bschedule\b|\broutine\b"
    r"|\bprogram(?:me)?\b|\bsplit\b|\b(?:all|every|each)\s+(?:the\s+)?days?\b|\bwork-?outs\b"
)
# "a good workout for abs" asks for advice, not for this plan.
_GENERIC_RE = re.compile(
    r"\b(?:a|an|any|some|good|best|great|quick|easy|hard|home|beginner|new|another|other)"
    rf"\s+{_WORKOUT}\b"
)
# The plan says nothing about food, kit, music, injuries or illness, and it
# cannot cancel or move a session.
_OFF_TOPIC_RE = re.compile(
    r"\b(?:eat|eating|food|meals?|diet|drink|drinks|protein|supplements?|calories|nutrition"
    r"|wear|clothes|outfit|shoes|trainers|music|playlist|songs?|sore|aching|injur\w*|hurts?"
    r"|pain|sick|ill|cold|flu|fever|cancel\w*|skip\w*|postpone|reschedule)\b"
)
# Telling Jarvis how a session went is not asking for the plan ("I just
# finished my workout"), unless a question comes with it.
_STATEMENT_RE = re.compile(
    r"\bi(?:'ve|\s+have)?\s+(?:just\s+|already\s+|really\s+)?(?:finished|completed|done|did"
    r"|missed|smashed|crushed|nailed|loved|enjoyed|hated|hate|love|enjoy)\b"
    r"|^(?:just\s+)?(?:finished|completed|did|done|missed|smashed|crushed|nailed)\b"
    r"(?!\s+(?:i|we|you)\b)"
    r"|\b(?:too\s+(?:tired|busy|lazy)|tired|exhausted|no\s+time|unmotivated|not\s+motivated)\b"
    rf"|\b(?:{_WORKOUT}|leg\s+day|session)\s+(?:is\s+|was\s+)?(?:done|over|finished|complete"
    r"|completed|great|good|hard|tough|brutal|awful|easy|fun|amazing|killer|rough|horrible"
    r"|terrible)\b"
)
_QUESTION_RE = re.compile(r"\b(?:what|what's|when|which|show|tell|is|does)\b")
_TODAY_RE = re.compile(
    r"^(?:(?:show|tell)\s+(?:me\s+)?)?(?:my\s+|the\s+)?work-?out$"
    r"|\b(?:my|our|the|next|this)\s+work-?out\b"
    r"|\bwhat(?:'s|\s+is)?\s+(?:the\s+|my\s+)?work-?out\b"
    r"|\bshould\s+(?:i|we)\b"
)


@dataclass(frozen=True)
class _Kind:
    """A kind of day, such as the lower-body days."""

    name: str
    noun: str
    ids: Tuple[str, ...]
    pattern: "re.Pattern[str]"
    # Days listed alongside, without counting as this kind.
    also: Tuple[str, ...] = ()


def _ids_with(*words: str) -> Tuple[str, ...]:
    return tuple(
        day.id
        for day in WEEK
        if any(re.search(rf"\b{word}\b", day.focus.lower()) for word in words)
    )


_KINDS: Tuple[_Kind, ...] = (
    _Kind(
        "lower-body",
        "a lower-body day",
        _ids_with("lower body"),
        re.compile(
            rf"\blegs?\s+days?\b|\blower[- ]body\b|\blegs?\s+{_WORKOUT}\b"
            rf"|\b{_WORKOUT}\s+for\s+(?:my\s+|the\s+)?legs\b"
        ),
    ),
    _Kind(
        "upper-body",
        "an upper-body day",
        _ids_with("upper body"),
        re.compile(
            rf"\barms?\s+days?\b|\bupper[- ]body\b|\barms?\s+{_WORKOUT}\b"
            rf"|\b{_WORKOUT}\s+for\s+(?:my\s+|the\s+)?arms\b"
        ),
    ),
    _Kind(
        "rest",
        "the rest day",
        _ids_with("rest"),
        re.compile(r"\brest\s+days?\b|\brest\s+(?:and|&)\s+recovery\b"),
        also=_ids_with("recovery"),
    ),
    _Kind(
        "recovery",
        "a recovery day",
        _ids_with("recovery"),
        re.compile(r"\brecovery\s+days?\b|\bactive\s+recovery\b"),
    ),
)


def _prepare(text: str) -> str:
    text = text.lower().replace("\u2019", "'").replace("\u2018", "'")
    text = re.sub(r"[^\w'&\s-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip(" '-")


def _day_reference(text: str, today: int) -> Optional[Tuple[int, str]]:
    """The first day the text names, as (index in WEEK, how to say it)."""

    found: List[Tuple[int, int, str]] = []
    for pattern, offset, when in _RELATIVE_DAYS:
        match = pattern.search(text)
        if match:
            found.append((match.start(), (today + offset) % 7, when))
    match = _WEEKDAY_RE.search(text)
    if match:
        index = [name.lower() for name in WEEKDAY_NAMES].index(match.group(1))
        found.append((match.start(), index, WEEKDAY_NAMES[index]))
    match = _ABBREVIATION_RE.search(text)
    if match:
        index = _ABBREVIATIONS[match.group("before") or match.group("after")]
        found.append((match.start(), index, WEEKDAY_NAMES[index]))
    if not found:
        return None
    _, index, when = min(found)
    return index, when


# ---------------------------------------------------------------------------
# Replies
# ---------------------------------------------------------------------------


def _join(names: List[str]) -> str:
    if len(names) < 3:
        return " and ".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _exercise_line(exercise: Exercise) -> str:
    parts = [part.strip() for part in exercise.stats.split("•") if part.strip()]
    if exercise.rounds > 1 and not any("rest" in part.lower() for part in parts):
        parts.append(f"{exercise.rest_seconds}s Rest")
    return (
        f"- {exercise.name}: {', '.join(parts)}. {exercise.notes} "
        f"Difficulty: {exercise.difficulty}."
    )


def _day_reply(day: Day, when: str, first: str = "") -> str:
    head = f"{day.title} (about {day.estimated_minutes} minutes)"
    if when in {"today", "tomorrow", "yesterday"}:
        head = f"{when.capitalize()}'s workout — {head}"
    lines = [first] if first else []
    lines += [head, day.description]
    lines += [_exercise_line(exercise) for exercise in day.exercises]
    for exercise in day.exercises:
        target = re.search(r"\d+\s*[–-]\s*\d+\s*BPM", exercise.stats)
        if target:
            lines.append(
                f"The {target.group(0)} heart-rate target comes from the original "
                "author's personal plan; targets vary with age and fitness."
            )
    lines += [SAFETY_NOTE, CREDIT]
    return "\n".join(lines)


def _brief(day: Day) -> str:
    names = ", ".join(exercise.name for exercise in day.exercises)
    return f"- {day.label}: {day.focus}, {day.estimated_minutes} min — {names}"


def _kind_reply(kind: _Kind, reference: Optional[Tuple[int, str]], today: int) -> str:
    lines = []
    if reference is not None:
        index, when = reference
        day = WEEK[index]
        if day.id in kind.ids:
            return _day_reply(day, when, first=f"Yes, {when} is {kind.noun}.")
        if when in WEEKDAY_NAMES:
            lines.append(f"No, {when} is {day.focus}.")
        else:
            lines.append(f"No, {when} is {day.title}.")
    days = [(index, day) for index, day in enumerate(WEEK) if day.id in kind.ids]
    names = [WEEKDAY_NAMES[index] for index, _ in days]
    are = "day is" if len(days) == 1 else "days are"
    heading = f"The plan's {kind.name} {are} {_join(names)}"
    for index, day in enumerate(WEEK):
        if day.id in kind.also and day.id not in kind.ids:
            heading += f", with {day.focus} on {WEEKDAY_NAMES[index]}"
    lines.append(f"{heading}:")
    lines += [_brief(day) for day in WEEK if day.id in kind.ids or day.id in kind.also]
    wait, index = min(((index - today) % 7, index) for index, _ in days)
    if wait == 0:
        lines.append("Today is one of them.")
        lines.append("Say 'today's workout' for the exercises.")
    else:
        name = WEEKDAY_NAMES[index]
        if wait == 1:
            lines.append(f"The next one is tomorrow, {name}.")
        else:
            lines.append(f"The next one is {name}, in {wait} days.")
        lines.append(f"Say '{name} workout' for the exercises.")
    lines.append(CREDIT)
    return "\n".join(lines)


def _week_reply(today: int) -> str:
    lines = [f"The {PROGRAM}:"]
    for index, day in enumerate(WEEK):
        mark = " (today)" if index == today else ""
        lines.append(f"- {day.label}: {day.focus}, {day.estimated_minutes} min{mark}")
    lines.append("Say 'today's workout' or a day, like 'Friday workout', for the exercises.")
    lines.append(CREDIT)
    return "\n".join(lines)


def usage() -> str:
    """How to ask about the workout plan."""

    return "\n".join(
        [
            f"I can show the {PROGRAM} from workout:",
            "- 'today's workout' or 'tomorrow's workout'",
            "- 'Friday workout' for any day's exercises",
            "- 'when is leg day?' or 'is today a rest day?'",
            "- 'weekly workout plan' for the whole week",
            CREDIT,
        ]
    )


def plan(text: str, now: date) -> Optional[str]:
    """Answer a question about the workout plan, or ``None`` if it isn't one.

    ``now`` (a datetime or date) decides what "today" and "tomorrow" mean.
    """

    prepared = whole = _prepare(text)
    if not prepared or _OFF_TOPIC_RE.search(prepared):
        return None
    if _STATEMENT_RE.search(prepared):
        # Keep just the question: "I did leg day yesterday, what's today's workout?"
        asked = [
            part
            for part in map(_prepare, re.split(r"[,.;:!?]+", text))
            if _QUESTION_RE.search(part) and not _STATEMENT_RE.search(part)
        ]
        if not asked:
            return None
        prepared = " ".join(asked)
    today = now.weekday()
    reference = _day_reference(prepared, today)
    about_plan = (
        _CONTEXT_RE.search(whole)
        or _SELF_CONTEXT_RE.search(whole)
        or (
            reference is not None
            and _EXERCISE_RE.search(whole)
            and not _GYM_VISIT_RE.search(whole)
        )
    )
    if not about_plan:
        return None
    for kind in _KINDS:
        if kind.pattern.search(prepared):
            if reference is None and _IS_IT_RE.search(prepared):
                reference = (today, "today")
            return _kind_reply(kind, reference, today)
    if reference is not None:
        index, when = reference
        return _day_reply(WEEK[index], when)
    if _GENERIC_RE.search(prepared):
        return None
    if _WEEK_RE.search(prepared):
        return _week_reply(today)
    if _TODAY_RE.search(prepared):
        return _day_reply(WEEK[today], "today")
    return None
