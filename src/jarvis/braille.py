"""Read and write Unicode braille using Grade 1 (uncontracted) English braille.

The module is dependency free and deterministic. :func:`read_braille` turns
braille cells such as ``⠓⠑⠇⠇⠕`` into plain text, while :func:`write_braille`
does the opposite. Only Grade 1 braille is supported: every letter is spelled
out, capitals are marked with the capital sign (dot 6) and numbers with the
number sign (dots 3-4-5-6).
"""

from __future__ import annotations

from typing import Dict, Iterable, Tuple

BLANK = "\u2800"
CAPITAL_SIGN = "\u2820"  # dot 6
NUMBER_SIGN = "\u283c"  # dots 3-4-5-6


class BrailleError(ValueError):
    """Raised when text or braille cannot be translated."""


def _cell(*dots: int) -> str:
    """Return the Unicode braille character made of ``dots`` (1-8)."""

    value = 0
    for dot in dots:
        value |= 1 << (dot - 1)
    return chr(0x2800 + value)


_LETTER_DOTS: Tuple[Tuple[str, Tuple[int, ...]], ...] = (
    ("a", (1,)),
    ("b", (1, 2)),
    ("c", (1, 4)),
    ("d", (1, 4, 5)),
    ("e", (1, 5)),
    ("f", (1, 2, 4)),
    ("g", (1, 2, 4, 5)),
    ("h", (1, 2, 5)),
    ("i", (2, 4)),
    ("j", (2, 4, 5)),
    ("k", (1, 3)),
    ("l", (1, 2, 3)),
    ("m", (1, 3, 4)),
    ("n", (1, 3, 4, 5)),
    ("o", (1, 3, 5)),
    ("p", (1, 2, 3, 4)),
    ("q", (1, 2, 3, 4, 5)),
    ("r", (1, 2, 3, 5)),
    ("s", (2, 3, 4)),
    ("t", (2, 3, 4, 5)),
    ("u", (1, 3, 6)),
    ("v", (1, 2, 3, 6)),
    ("w", (2, 4, 5, 6)),
    ("x", (1, 3, 4, 6)),
    ("y", (1, 3, 4, 5, 6)),
    ("z", (1, 3, 5, 6)),
)

_PUNCTUATION_DOTS: Tuple[Tuple[str, Tuple[int, ...]], ...] = (
    (",", (2,)),
    (";", (2, 3)),
    (":", (2, 5)),
    (".", (2, 5, 6)),
    ("?", (2, 3, 6)),
    ("!", (2, 3, 5)),
    ("'", (3,)),
    ("-", (3, 6)),
    ("/", (3, 4)),
    ("\u201c", (2, 3, 6)),
    ("\u201d", (3, 5, 6)),
)

# Digits reuse the first ten letters after the number sign: 1-9 then 0.
_DIGIT_LETTERS = "abcdefghij"

LETTER_TO_CELL: Dict[str, str] = {
    letter: _cell(*dots) for letter, dots in _LETTER_DOTS
}
CELL_TO_LETTER: Dict[str, str] = {
    cell: letter for letter, cell in LETTER_TO_CELL.items()
}

PUNCTUATION_TO_CELL: Dict[str, str] = {
    mark: _cell(*dots) for mark, dots in _PUNCTUATION_DOTS
}
# The first spelling of a shared cell wins when reading, so "?" beats "“".
CELL_TO_PUNCTUATION: Dict[str, str] = {}
for _mark, _cell_char in PUNCTUATION_TO_CELL.items():
    CELL_TO_PUNCTUATION.setdefault(_cell_char, _mark)

DIGIT_TO_CELL: Dict[str, str] = {
    str((index + 1) % 10): LETTER_TO_CELL[letter]
    for index, letter in enumerate(_DIGIT_LETTERS)
}
CELL_TO_DIGIT: Dict[str, str] = {
    cell: digit for digit, cell in DIGIT_TO_CELL.items()
}


def is_braille(text: str) -> bool:
    """Return ``True`` when ``text`` contains at least one braille cell."""

    return any("\u2800" <= char <= "\u28ff" for char in text)


def dots_for(cell: str) -> Tuple[int, ...]:
    """Return the dot numbers that make up a single braille ``cell``."""

    if len(cell) != 1 or not "\u2800" <= cell <= "\u28ff":
        raise BrailleError("That is not a single braille cell.")
    value = ord(cell) - 0x2800
    return tuple(dot for dot in range(1, 9) if value & (1 << (dot - 1)))


def write_braille(text: str) -> str:
    """Translate plain ``text`` into Unicode braille cells."""

    if not text or not text.strip():
        raise BrailleError("Give me some text to translate into braille.")

    cells: list[str] = []
    in_number = False
    for char in text:
        if char.isspace():
            cells.append(BLANK if char == " " else char)
            in_number = False
            continue
        if char.isdigit():
            if not in_number:
                cells.append(NUMBER_SIGN)
                in_number = True
            cells.append(DIGIT_TO_CELL[char])
            continue
        in_number = False
        lowered = char.lower()
        if lowered in LETTER_TO_CELL:
            if char.isupper():
                cells.append(CAPITAL_SIGN)
            cells.append(LETTER_TO_CELL[lowered])
            continue
        if char in PUNCTUATION_TO_CELL:
            cells.append(PUNCTUATION_TO_CELL[char])
            continue
        raise BrailleError(
            f"I do not have a Grade 1 braille cell for '{char}' yet."
        )
    return "".join(cells)


def read_braille(cells: str) -> str:
    """Translate Unicode braille ``cells`` into plain text."""

    if not cells or not cells.strip():
        raise BrailleError("Give me some braille cells to read.")
    if not is_braille(cells):
        raise BrailleError(
            "I could not find any braille cells there. Braille looks like ⠓⠑⠇⠇⠕."
        )

    letters: list[str] = []
    capital_next = False
    in_number = False
    for char in cells:
        if char.isspace() or char == BLANK:
            letters.append(" " if char == BLANK else char)
            capital_next = False
            in_number = False
            continue
        if char == CAPITAL_SIGN:
            capital_next = True
            in_number = False
            continue
        if char == NUMBER_SIGN:
            in_number = True
            capital_next = False
            continue
        if in_number and char in CELL_TO_DIGIT:
            letters.append(CELL_TO_DIGIT[char])
            continue
        in_number = False
        if char in CELL_TO_LETTER:
            letter = CELL_TO_LETTER[char]
            letters.append(letter.upper() if capital_next else letter)
            capital_next = False
            continue
        if char in CELL_TO_PUNCTUATION:
            letters.append(CELL_TO_PUNCTUATION[char])
            capital_next = False
            continue
        raise BrailleError(
            f"I do not recognise the braille cell '{char}' (dots "
            f"{'-'.join(str(dot) for dot in dots_for(char)) or 'none'})."
        )
    return "".join(letters)


def alphabet_chart() -> str:
    """Return a short chart of the braille alphabet."""

    lines: Iterable[str] = (
        f"{letter} {cell}" for letter, cell in LETTER_TO_CELL.items()
    )
    return "  ".join(lines)
