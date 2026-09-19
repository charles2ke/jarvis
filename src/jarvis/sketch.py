"""A small offline gallery of ASCII sketches used by the ``sketch`` skill.

Every sketch is hand drawn with plain ASCII so it renders in any terminal. The
module is dependency free and deterministic: :func:`lookup` finds a sketch by
name or alias (tolerating small typos) and :func:`render` turns it into the
lines Jarvis prints.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from textwrap import dedent
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Sketch:
    """A named ASCII drawing and the caption that goes with it."""

    subject: str
    art: str
    caption: str
    aliases: Sequence[str] = field(default_factory=tuple)

    @property
    def keys(self) -> Tuple[str, ...]:
        return (self.subject, *self.aliases)

    def lines(self) -> List[str]:
        """Return the drawing as a list of lines, without blank edges."""

        rows = dedent(self.art).strip("\n").splitlines()
        return [row.rstrip() for row in rows]


SKETCHES: Tuple[Sketch, ...] = (
    Sketch(
        subject="cat",
        art=r"""
         /\_/\
        ( o.o )
         > ^ <
        """,
        caption="One cat, drawn in six whiskers or fewer.",
        aliases=("kitten", "kitty", "a cat"),
    ),
    Sketch(
        subject="dog",
        art=r"""
         __
        /  \__
        |      \
        |  O  O |
        \___^___/
          |  |
        """,
        caption="A very good dog.",
        aliases=("puppy", "a dog"),
    ),
    Sketch(
        subject="house",
        art=r"""
            /\
           /  \
          /____\
          |    |
          | [] |
          |____|
        """,
        caption="A little house with the light left on.",
        aliases=("home", "a house", "cottage"),
    ),
    Sketch(
        subject="tree",
        art=r"""
           ***
          *****
         *******
          *****
            |
            |
        """,
        caption="A tree, roughly in summer.",
        aliases=("a tree", "pine", "forest"),
    ),
    Sketch(
        subject="flower",
        art=r"""
          _(_)_
         (_)@(_)
           (_)
            |
           \|/
        """,
        caption="A flower for you.",
        aliases=("a flower", "rose", "daisy"),
    ),
    Sketch(
        subject="boat",
        art=r"""
            |\
            | \
            |  \
            |___\
        \___________/
         ~~~~~~~~~~~
        """,
        caption="A sailing boat with a following wind.",
        aliases=("a boat", "ship", "sailboat", "yacht"),
    ),
    Sketch(
        subject="rocket",
        art=r"""
            /\
           /  \
          |    |
          | [] |
          |____|
          /_\/_\
           '  '
        """,
        caption="A rocket, ready when you are.",
        aliases=("a rocket", "spaceship", "space ship"),
    ),
    Sketch(
        subject="star",
        art=r"""
            *
           ***
        *********
          *****
         **   **
        """,
        caption="A star, for the good days.",
        aliases=("a star",),
    ),
    Sketch(
        subject="heart",
        art=r"""
         **   **
        *******
        *******
         *****
          ***
           *
        """,
        caption="A heart, no occasion needed.",
        aliases=("a heart", "love heart"),
    ),
    Sketch(
        subject="sun",
        art=r"""
          \  |  /
           .---.
        -- (   ) --
           '---'
          /  |  \
        """,
        caption="The sun, doing its best.",
        aliases=("the sun", "sunshine"),
    ),
    Sketch(
        subject="moon",
        art=r"""
           _..._
         .'     '.
        :         :
        :        .'
         '.   _.'
           '''
        """,
        caption="A crescent moon over a quiet night.",
        aliases=("the moon", "crescent moon"),
    ),
    Sketch(
        subject="cloud",
        art=r"""
           .--.
        .-(    ).
        (___.__)__)
        """,
        caption="A cloud with nowhere to be.",
        aliases=("a cloud", "clouds"),
    ),
    Sketch(
        subject="mountain",
        art=r"""
            /\
           /  \
          / /\ \
         / /  \ \
        /_/    \_\
        """,
        caption="A mountain worth the walk.",
        aliases=("a mountain", "mountains", "hill"),
    ),
    Sketch(
        subject="fish",
        art=r"""
           /\
         ><  °>
           \/
        """,
        caption="One fish, swimming left to right.",
        aliases=("a fish",),
    ),
    Sketch(
        subject="bird",
        art=r"""
          \    /
           \__/
           (o )>
        """,
        caption="A bird mid-flap.",
        aliases=("a bird", "birds"),
    ),
    Sketch(
        subject="robot",
        art=r"""
         [======]
         | o  o |
         |  __  |
         |______|
          /|  |\
        """,
        caption="A robot. Family, in a way.",
        aliases=("a robot", "android"),
    ),
    Sketch(
        subject="coffee",
        art=r"""
          ( (
           ) )
         ________
        |        |]
        \        /
         '------'
        """,
        caption="Coffee, still hot.",
        aliases=("a coffee", "cup of coffee", "coffee cup", "tea", "mug"),
    ),
    Sketch(
        subject="smiley face",
        art=r"""
          .-''-.
         /  o o \
        |    ^   |
        |  \__/  |
         \      /
          '-..-'
        """,
        caption="A friendly face.",
        aliases=("smiley", "face", "a face", "smile", "happy face"),
    ),
)


def _normalise(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    for article in ("a ", "an ", "the ", "some ", "me a ", "me an ", "me the "):
        if cleaned.startswith(article):
            cleaned = cleaned[len(article):].strip()
    return cleaned


def _build_index(sketches: Sequence[Sketch]) -> Dict[str, Sketch]:
    index: Dict[str, Sketch] = {}
    for sketch in sketches:
        for key in sketch.keys:
            index.setdefault(_normalise(key), sketch)
    return index


_INDEX: Dict[str, Sketch] = _build_index(SKETCHES)


def subjects() -> List[str]:
    """Return the subjects Jarvis can sketch, alphabetically."""

    return sorted(sketch.subject for sketch in SKETCHES)


def lookup(query: str) -> Optional[Sketch]:
    """Return the sketch matching ``query``, or ``None``.

    Matching ignores case, punctuation and leading articles, understands
    aliases and tolerates small typos.
    """

    key = _normalise(query)
    if not key:
        return None
    sketch = _INDEX.get(key)
    if sketch is not None:
        return sketch
    close = get_close_matches(key, list(_INDEX), n=1, cutoff=0.82)
    if close:
        return _INDEX[close[0]]
    return None


def suggestions(query: str, limit: int = 3) -> List[str]:
    """Return subjects that look similar to ``query``."""

    key = _normalise(query)
    if not key:
        return []
    matches = get_close_matches(key, list(_INDEX), n=limit * 2, cutoff=0.5)
    found: List[str] = []
    for match in matches:
        subject = _INDEX[match].subject
        if subject not in found:
            found.append(subject)
        if len(found) == limit:
            break
    return found


def render(sketch: Sketch) -> str:
    """Return the drawing and its caption as one printable block."""

    return "\n".join([*sketch.lines(), "", sketch.caption])
