"""Write short original poems offline.

The module is dependency free and deterministic when a ``seed`` is supplied.
:func:`write_poem` composes a poem about a topic in one of the supported forms
(:data:`FORMS`) by filling curated word banks and templates, so every poem is
newly assembled rather than recited from a fixed list.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

FORMS: Tuple[str, ...] = ("haiku", "limerick", "acrostic", "couplet", "verse")

DEFAULT_TOPIC = "the quiet hour"

FORM_DESCRIPTIONS: Tuple[Tuple[str, str], ...] = (
    ("haiku", "three unrhymed lines of five, seven and five syllables"),
    ("limerick", "five bouncing lines rhyming A-A-B-B-A"),
    ("acrostic", "one line per letter of your word, spelling it down the page"),
    ("couplet", "two rhyming lines"),
    ("verse", "four lines of free verse (the default)"),
)

_FORM_ALIASES: Dict[str, str] = {
    "haiku": "haiku",
    "haikus": "haiku",
    "limerick": "limerick",
    "limericks": "limerick",
    "acrostic": "acrostic",
    "acrostics": "acrostic",
    "couplet": "couplet",
    "couplets": "couplet",
    "rhyme": "couplet",
    "rhyming": "couplet",
    "verse": "verse",
    "poem": "verse",
    "poems": "verse",
    "poetry": "verse",
    "ode": "verse",
    "free verse": "verse",
}

_FORM_PATTERN = re.compile(
    r"\b(free verse|haikus?|limericks?|acrostics?|couplets?|rhyming|rhyme)\b",
    re.IGNORECASE,
)


class PoetryError(ValueError):
    """Raised when a poem cannot be written."""


@dataclass(frozen=True)
class Poem:
    """A finished poem."""

    title: str
    form: str
    lines: Tuple[str, ...]

    def render(self) -> str:
        """Return the poem as displayable text."""

        return "\n".join((f"{self.title} ({self.form})", "", *self.lines))


# Short phrases used to pad metred lines. They are grouped by the syllable
# count reported by :func:`count_syllables`, so the metre Jarvis promises and
# the metre it measures always agree.
_FRAGMENT_BANK: Tuple[str, ...] = (
    "stays",
    "waits",
    "turns",
    "holds",
    "sings",
    "returns",
    "goes quiet",
    "keeps time",
    "drifts on",
    "in the rain",
    "before dawn",
    "at the window",
    "under the stars",
    "settles into dusk",
    "answers with the light",
    "learns a slower song",
    "the morning is wide",
    "a small lamp burning",
    "nothing is hurried",
    "snow on the rooftops",
    "the sky begins again",
    "and the kettle is warm",
    "and the clocks lose their grip",
    "while the city sleeps on",
    "the long road remembers rain",
    "a window full of morning",
    "and still the river arrives",
    "patient as an open hand",
)


_OPENERS: Tuple[str, ...] = (
    "I keep",
    "Here is",
    "Somewhere",
    "Again",
    "Even now",
    "Listen:",
)

_IMAGES: Tuple[str, ...] = (
    "a lamp left on for no one",
    "rain revising the window",
    "the long patience of stone",
    "a door that learns the wind",
    "footprints the tide will edit",
    "the small weather of a room",
    "an hour with nothing to prove",
    "light doing its quiet arithmetic",
)

_ACTIONS: Tuple[str, ...] = (
    "keeps its own hours",
    "refuses to hurry",
    "answers in weather",
    "outlasts the argument",
    "begins again without asking",
    "carries what it cannot name",
)

_CLOSERS: Tuple[str, ...] = (
    "and that is enough for tonight.",
    "and nothing else is required.",
    "and the morning agrees.",
    "so I stay a little longer.",
    "and I call it kindness.",
)

_COUPLETS: Tuple[Tuple[str, str], ...] = (
    ("{topic} arrives without a sound,", "and leaves its fingerprints around."),
    ("{topic} is a lamp I carry late,", "small enough to balance fate."),
    ("Say {topic} once and mean it twice,", "the second time is worth the price."),
    ("{topic} will not be hurried through,", "it keeps the slow hours honest too."),
    ("I learned {topic} the longer way,", "and kept the lesson anyway."),
)

_LIMERICKS: Tuple[Tuple[str, ...], ...] = (
    (
        "A fellow who pondered {topic} all day",
        "decided to do it his way.",
        "He measured the hours,",
        "he counted the flowers,",
        "and still had the evening to play.",
    ),
    (
        "There once was a student of {topic} in Kent",
        "who never was sure what it meant.",
        "She studied all night",
        "by one wobbly light",
        "and found it was time rather well spent.",
    ),
    (
        "I carried my questions of {topic} to bed",
        "and left them to argue instead.",
        "They rattled the door,",
        "then slept on the floor,",
        "and woke with a plan in my head.",
    ),
)


_ACROSTIC_LINES: Dict[str, Tuple[str, ...]] = {
    "a": ("Always the first light on the sill,", "An answer that waits to be asked,"),
    "b": ("Begin where the noise gives way,", "Between one breath and the next,"),
    "c": ("Carry it gently, it is older than you,", "Comes back like weather,"),
    "d": ("Down where the roots keep their counsel,", "Daylight, unhurried and fair,"),
    "e": ("Every ordinary hour is a door,", "Even the silence is saying something,"),
    "f": ("Find the small thing and keep it,", "Fields of it, wide as patience,"),
    "g": ("Gather what the day left out,", "Gone soft at the edges, like rain,"),
    "h": ("Here, in the middle of the week,", "Hold it loosely and it stays,"),
    "i": ("If it returns, let it,", "In the end the quiet wins,"),
    "j": ("Just enough light to go on,", "Joy arrives in ordinary shoes,"),
    "k": ("Keep the window open a little,", "Known by heart, and still surprising,"),
    "l": ("Leaning towards the morning,", "Long after the lamps go out,"),
    "m": ("Morning writes its first draft,", "Made of patience and small repairs,"),
    "n": ("Nothing is wasted that was true,", "Night sets the table anyway,"),
    "o": ("Open hands hold the most,", "Once, and then always after,"),
    "p": ("Patience is a kind of weather,", "Put down the hurry for an hour,"),
    "q": ("Quietly, the way rivers work,", "Quick to forgive the morning,"),
    "r": ("Rain rewrites the same sentence,", "Room enough for both of us,"),
    "s": ("Say it plainly and mean it,", "Slowly, the way trees decide,"),
    "t": ("The small hours keep good company,", "Turning towards the light again,"),
    "u": ("Under all of it, a steady thing,", "Unhurried, and therefore true,"),
    "v": ("Very late, the house agrees,", "Voices carry further at dusk,"),
    "w": ("Worth the waiting, worth the walk,", "Weather comes and goes, and stays,"),
    "x": ("Exactly here, and nowhere else,", "Exit the noise, enter the hour,"),
    "y": ("Yes, even now, especially now,", "Yesterday keeps sending letters,"),
    "z": ("Zero hurry in the whole of it,", "Zealous only about small joys,"),
}

_GENERIC_ACROSTIC: Tuple[str, ...] = (
    "Light gets in where the hinge gives way,",
    "Another ordinary miracle,",
    "Softly, and then all at once,",
)


def forms() -> Tuple[str, ...]:
    """Return the poem forms Jarvis can write."""

    return FORMS


def detect_form(text: str) -> Optional[str]:
    """Return the poem form named in ``text``, if any."""

    found = _FORM_PATTERN.search(text or "")
    if found is None:
        return None
    return _FORM_ALIASES.get(found.group(1).lower())


def normalise_form(form: Optional[str]) -> str:
    """Return a supported form name, defaulting to free verse."""

    if not form:
        return "verse"
    resolved = _FORM_ALIASES.get(form.strip().lower())
    if resolved is None:
        raise PoetryError(
            f"I cannot write a '{form}'. I know: " + ", ".join(FORMS) + "."
        )
    return resolved


def count_syllables(text: str) -> int:
    """Estimate the number of syllables in ``text``."""

    total = 0
    for word in re.findall(r"[a-z']+", text.lower()):
        groups = re.findall(r"[aeiouy]+", word)
        count = len(groups)
        if count > 1 and word.endswith("e") and not word.endswith(("le", "ee", "ye")):
            count -= 1
        total += max(count, 1)
    return total


def _fragments_by_syllables() -> Dict[int, Tuple[str, ...]]:
    grouped: Dict[int, List[str]] = {}
    for fragment in _FRAGMENT_BANK:
        grouped.setdefault(count_syllables(fragment), []).append(fragment)
    return {size: tuple(values) for size, values in grouped.items()}


_FRAGMENTS: Dict[int, Tuple[str, ...]] = _fragments_by_syllables()


def _tidy_topic(topic: str) -> str:
    cleaned = re.sub(r"\s+", " ", (topic or "").strip().strip("\"'"))
    cleaned = re.sub(r"^(?:a|an|the)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.rstrip(".?!,")
    return cleaned or DEFAULT_TOPIC


def _title(topic: str) -> str:
    words = topic.split()
    return " ".join(word[0].upper() + word[1:] if word else word for word in words)


def _pad(rng: random.Random, target: int) -> str:
    """Return a phrase of roughly ``target`` syllables."""

    parts: List[str] = []
    remaining = target
    while remaining > 0:
        sizes = [size for size in sorted(_FRAGMENTS, reverse=True) if size <= remaining]
        if not sizes:
            break
        choice = rng.choice(_FRAGMENTS[sizes[0]])
        parts.append(choice)
        remaining -= sizes[0]
    return " ".join(parts)


def _metred_line(rng: random.Random, topic: str, target: int, lead: bool) -> str:
    """Return a line of about ``target`` syllables, naming ``topic`` if it fits."""

    if lead:
        used = count_syllables(topic)
        if used <= target:
            padding = _pad(rng, target - used)
            return f"{topic} {padding}".strip()
        return topic
    return _pad(rng, target) or topic


def _haiku(rng: random.Random, topic: str) -> Tuple[str, ...]:
    return (
        _metred_line(rng, topic, 5, lead=True),
        _metred_line(rng, topic, 7, lead=False),
        _metred_line(rng, topic, 5, lead=False),
    )


def _limerick(rng: random.Random, topic: str) -> Tuple[str, ...]:
    template = rng.choice(_LIMERICKS)
    return tuple(line.replace("{topic}", topic) for line in template)


def _couplet(rng: random.Random, topic: str) -> Tuple[str, ...]:
    first, second = rng.choice(_COUPLETS)
    return (
        first.replace("{topic}", _title(topic)),
        second.replace("{topic}", topic),
    )


def _acrostic(rng: random.Random, topic: str) -> Tuple[str, ...]:
    letters = [character for character in topic if character.isalnum()]
    if not letters:
        raise PoetryError("An acrostic needs a word with letters in it.")
    letters = letters[:16]
    lines: List[str] = []
    for letter in letters:
        options = _ACROSTIC_LINES.get(letter.lower())
        if options:
            lines.append(rng.choice(options))
        else:
            filler = rng.choice(_GENERIC_ACROSTIC)
            lines.append(f"{letter.upper()} — {filler}")
    return tuple(lines)


def _verse(rng: random.Random, topic: str) -> Tuple[str, ...]:
    images = rng.sample(_IMAGES, 2)
    return (
        f"{rng.choice(_OPENERS)} {topic} like {images[0]},",
        f"{_title(topic)} {rng.choice(_ACTIONS)},",
        f"a small proof that {images[1]} is still here,",
        rng.choice(_CLOSERS),
    )


_WRITERS = {
    "haiku": _haiku,
    "limerick": _limerick,
    "acrostic": _acrostic,
    "couplet": _couplet,
    "verse": _verse,
}


def write_poem(
    topic: str = "",
    form: Optional[str] = None,
    seed: Optional[int] = None,
) -> Poem:
    """Compose a poem about ``topic`` in ``form``.

    ``seed`` makes the result reproducible; without it every call writes a
    fresh poem.
    """

    resolved = normalise_form(form)
    subject = _tidy_topic(topic)
    rng = random.Random(seed)
    lines = _WRITERS[resolved](rng, subject)
    return Poem(title=_title(subject), form=resolved, lines=tuple(lines))


def form_lines() -> Sequence[str]:
    """Return one description per supported poem form."""

    return [f"- {name}: {description}" for name, description in FORM_DESCRIPTIONS]
