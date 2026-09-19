"""Natural language to text helpers.

This module turns loosely written input into the plain, canonical text the
rest of Jarvis understands:

* :func:`number_to_words` and :func:`words_to_number` convert between digits
  and their English spelling.
* :func:`flatten` collapses multi-line input and literal escape sequences
  (``\\n``, ``\\t``) into a single line of text.
* :func:`normalize` applies both of the above plus a few polite-prefix and
  operator rewrites so that free-form phrasing reaches the right skill.
"""

from __future__ import annotations

import re
from typing import Optional

__all__ = ["flatten", "normalize", "number_to_words", "words_to_number"]


UNITS = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)

TENS = (
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
)

SCALES = (
    (1_000_000_000_000, "trillion"),
    (1_000_000_000, "billion"),
    (1_000_000, "million"),
    (1_000, "thousand"),
    (100, "hundred"),
)

MAX_SPELLABLE = 10 ** 15

_UNIT_VALUES = {word: value for value, word in enumerate(UNITS)}
_TENS_VALUES = {word: index * 10 for index, word in enumerate(TENS) if word}
_SCALE_VALUES = {word: value for value, word in SCALES}
_NUMBER_WORDS = set(_UNIT_VALUES) | set(_TENS_VALUES) | set(_SCALE_VALUES) | {"and"}

_SMART_CHARACTERS = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u00a0": " ",
}

_ESCAPES = {
    r"\n": " ",
    r"\r": " ",
    r"\t": " ",
    r"\\": " ",
}

_POLITE_PREFIX = re.compile(
    r"^\s*(?:(?:hey|ok|okay)\s+)?jarvis[,:]?\s+(?=\S)|"
    r"^\s*(?:please|kindly)[,:]?\s+(?=\S)|"
    r"^\s*(?:could|can|would|will)\s+you\s+(?:please\s+)?(?=\S)",
    re.IGNORECASE,
)

_POLITE_SUFFIX = re.compile(r"[,\s]+please\s*([.?!]*)\s*$", re.IGNORECASE)

_OPERATOR_WORDS = (
    (r"\b(?:multiplied\s+by|times)\b", "*"),
    (r"\b(?:divided\s+by|over)\b", "/"),
    (r"\b(?:plus|added\s+to)\b", "+"),
    (r"\b(?:minus|subtract(?:ed\s+by)?|less)\b", "-"),
)

_NUMBER_PHRASE = re.compile(
    r"\b(?:negative[\s-]+)?(?:"
    + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
    + r")"
    r"(?:[\s-]+(?:" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + r"))*\b",
    re.IGNORECASE,
)


def number_to_words(value: int) -> str:
    """Return the English spelling of the integer ``value``.

    Raises :class:`ValueError` when ``value`` is too large to spell.
    """

    number = int(value)
    if abs(number) >= MAX_SPELLABLE:
        raise ValueError("That number is too large for me to spell out.")
    if number < 0:
        return f"minus {number_to_words(-number)}"
    return _spell(number)


def _spell(number: int) -> str:
    if number < 20:
        return UNITS[number]
    if number < 100:
        tens, unit = divmod(number, 10)
        word = TENS[tens]
        return f"{word}-{UNITS[unit]}" if unit else word
    for scale, name in SCALES:
        if number >= scale:
            count, remainder = divmod(number, scale)
            words = f"{_spell(count)} {name}"
            if remainder:
                joiner = " and " if remainder < 100 else " "
                words = f"{words}{joiner}{_spell(remainder)}"
            return words
    raise ValueError("That number is too large for me to spell out.")


def words_to_number(text: str) -> Optional[int]:
    """Return the integer spelled out by ``text`` or ``None``.

    ``"twenty-one"`` and ``"one hundred and five"`` both parse; anything that
    is not a pure number phrase returns ``None``.
    """

    tokens = [token for token in re.split(r"[\s-]+", (text or "").strip().lower()) if token]
    if not tokens:
        return None
    negative = False
    if tokens[0] in {"minus", "negative"}:
        negative = True
        tokens = tokens[1:]
    if not tokens or any(token not in _NUMBER_WORDS for token in tokens):
        return None
    if all(token == "and" for token in tokens):
        return None

    total = 0
    current = 0
    seen = False
    for token in tokens:
        if token == "and":
            continue
        if token in _UNIT_VALUES:
            current += _UNIT_VALUES[token]
        elif token in _TENS_VALUES:
            current += _TENS_VALUES[token]
        else:
            scale = _SCALE_VALUES[token]
            if scale == 100:
                current = (current or 1) * scale
            else:
                total += (current or 1) * scale
                current = 0
        seen = True
    if not seen:
        return None
    result = total + current
    try:
        canonical = re.split(r"[\s-]+", number_to_words(result))
    except ValueError:
        return None
    if tokens != canonical and (
        "and" in tokens or tokens != [token for token in canonical if token != "and"]
    ):
        return None
    return -result if negative else result


def flatten(text: str) -> str:
    """Return ``text`` as a single line with escapes and smart characters resolved."""

    flattened = text or ""
    for source, replacement in _SMART_CHARACTERS.items():
        flattened = flattened.replace(source, replacement)
    for source, replacement in _ESCAPES.items():
        flattened = flattened.replace(source, replacement)
    return re.sub(r"\s+", " ", flattened).strip()


def normalize(text: str) -> str:
    """Return the canonical single-line command hidden inside ``text``."""

    normalized = flatten(text)
    if not normalized:
        return ""
    previous = None
    while previous != normalized:
        previous = normalized
        normalized = _POLITE_PREFIX.sub("", normalized, count=1).strip()
    normalized = _POLITE_SUFFIX.sub(r"\1", normalized).strip()
    normalized = _replace_number_words(normalized)
    for pattern, replacement in _OPERATOR_WORDS:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", normalized).strip()


def _replace_number_words(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        value = words_to_number(match.group(0))
        return match.group(0) if value is None else str(value)

    return _NUMBER_PHRASE.sub(replace, text)
