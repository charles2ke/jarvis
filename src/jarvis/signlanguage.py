"""A small offline sign language guide used by the ``sign-language`` skill.

The data set describes American Sign Language (ASL) in words: the manual
alphabet, the number handshapes and a hand-curated set of everyday signs.
Descriptions are written so they can be followed from a terminal; they are a
starting point, not a replacement for learning from Deaf teachers and native
signers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Dict, List, Optional, Sequence, Tuple


LANGUAGE = "American Sign Language (ASL)"


@dataclass(frozen=True)
class Sign:
    """A single sign: what it means and how it is produced."""

    term: str
    description: str
    aliases: Sequence[str] = field(default_factory=tuple)

    @property
    def keys(self) -> Tuple[str, ...]:
        return (self.term, *self.aliases)


ALPHABET: Dict[str, str] = {
    "A": "a fist with the thumb straight up alongside the index finger",
    "B": "a flat hand, fingers together and pointing up, thumb folded across the palm",
    "C": "a curved hand shaped like the letter C, palm facing sideways",
    "D": "index finger up, the other fingertips meeting the thumb in a circle",
    "E": "fingertips curled down onto the thumb, which lies across the palm",
    "F": "index finger and thumb touching in a circle, the other three fingers up",
    "G": "a fist turned sideways with the index finger and thumb held parallel",
    "H": "a fist turned sideways with the index and middle fingers extended together",
    "I": "a fist with only the little finger pointing up",
    "J": "the letter I traced downward to draw a J in the air",
    "K": "index and middle fingers in a V, thumb touching the middle finger's base",
    "L": "index finger up and thumb out, making an L shape",
    "M": "thumb tucked under the index, middle and ring fingers of a fist",
    "N": "thumb tucked under the index and middle fingers of a fist",
    "O": "all fingertips meeting the thumb to form a round O",
    "P": "the K handshape pointed downward",
    "Q": "the G handshape pointed downward",
    "R": "index and middle fingers crossed, pointing up",
    "S": "a closed fist with the thumb crossing the front of the fingers",
    "T": "a fist with the thumb poking up between the index and middle fingers",
    "U": "index and middle fingers extended together, pointing up",
    "V": "index and middle fingers extended apart in a V, pointing up",
    "W": "index, middle and ring fingers extended and spread, thumb on the little finger",
    "X": "a fist with the index finger bent into a hook",
    "Y": "a fist with the thumb and little finger extended",
    "Z": "the index finger drawing a Z in the air",
}


DIGITS: Dict[str, str] = {
    "0": "the O handshape: fingertips and thumb touching in a circle",
    "1": "index finger pointing up, the other fingers closed",
    "2": "index and middle fingers up and apart, palm forward",
    "3": "thumb, index and middle fingers extended",
    "4": "four fingers up and spread, thumb folded across the palm",
    "5": "an open hand, all five fingers spread",
    "6": "little finger touching the thumb, the other three fingers up",
    "7": "ring finger touching the thumb, the other three fingers up",
    "8": "middle finger touching the thumb, the other three fingers up",
    "9": "index finger touching the thumb, the other three fingers up",
}


SIGNS: Tuple[Sign, ...] = (
    Sign(
        term="hello",
        description=(
            "Touch the fingertips of a flat hand to your forehead near the "
            "eyebrow and move the hand forward and away, like a relaxed salute, "
            "with a smile."
        ),
        aliases=("hi", "hey", "greetings"),
    ),
    Sign(
        term="goodbye",
        description="Wave an open hand, or open and close the fingers toward the palm.",
        aliases=("bye", "see you", "farewell"),
    ),
    Sign(
        term="thank you",
        description=(
            "Touch the fingertips of a flat hand to your chin, then move the "
            "hand forward and down toward the person you are thanking."
        ),
        aliases=("thanks", "thank you very much"),
    ),
    Sign(
        term="please",
        description="Rub a flat open hand in a circle over the centre of your chest.",
    ),
    Sign(
        term="sorry",
        description=(
            "Make a fist with the thumb alongside (the letter A) and rub it in a "
            "circle over your chest, with an apologetic expression."
        ),
        aliases=("apologise", "apologize", "my apologies"),
    ),
    Sign(
        term="yes",
        description="Make a fist and nod it up and down at the wrist, like a head nodding.",
    ),
    Sign(
        term="no",
        description=(
            "Snap the index and middle fingers down onto the thumb once, as if a "
            "mouth were closing."
        ),
    ),
    Sign(
        term="help",
        description=(
            "Rest a thumbs-up fist on the flat palm of the other hand and lift "
            "both hands together; push them toward someone to offer help, or "
            "toward yourself to ask for it."
        ),
        aliases=("help me", "i need help"),
    ),
    Sign(
        term="understand",
        description=(
            "Hold a fist near your forehead and flick the index finger up, as if "
            "an idea just switched on. Shake your head while signing it for "
            "'don't understand'."
        ),
        aliases=("i understand", "do you understand", "got it"),
    ),
    Sign(
        term="learn",
        description=(
            "Take information from the flat palm of one hand with the fingertips "
            "of the other and lift it to your forehead."
        ),
        aliases=("study", "learning"),
    ),
    Sign(
        term="sign language",
        description=(
            "Point both index fingers and circle them alternately toward each "
            "other in front of you for SIGN, then bring flat 'L' hands together "
            "and draw them apart for LANGUAGE."
        ),
        aliases=("asl", "signing", "sign"),
    ),
    Sign(
        term="deaf",
        description=(
            "Touch the index finger near your ear and then near the corner of "
            "your mouth (or the reverse), tracing the path between them."
        ),
    ),
    Sign(
        term="hearing",
        description=(
            "Circle the index finger forward in small rolls in front of your "
            "lips, showing speech."
        ),
    ),
    Sign(
        term="name",
        description=(
            "Cross the index and middle fingers of both hands (the H handshape) "
            "and tap the top pair twice on the bottom pair."
        ),
        aliases=("my name is", "what is your name"),
    ),
    Sign(
        term="how are you",
        description=(
            "Hook both curved hands together, palms in, and roll them up and out "
            "for HOW, then point at the person for YOU, with raised eyebrows."
        ),
        aliases=("how are you doing",),
    ),
    Sign(
        term="nice to meet you",
        description=(
            "Slide one flat hand across the other for NICE, then bring two "
            "upright index fingers together for MEET, and point at the person."
        ),
        aliases=("pleased to meet you",),
    ),
    Sign(
        term="i love you",
        description=(
            "Hold up the thumb, index finger and little finger of one hand, palm "
            "forward: the combined handshape for I, L and Y."
        ),
        aliases=("ily", "love you"),
    ),
    Sign(
        term="love",
        description="Cross both fists over your chest, as though hugging yourself.",
    ),
    Sign(
        term="friend",
        description=(
            "Hook the bent index fingers together, then swap which finger is on "
            "top."
        ),
        aliases=("friends", "best friend"),
    ),
    Sign(
        term="family",
        description=(
            "Make the F handshape with both hands, palms facing out, and circle "
            "them outward until the little fingers meet."
        ),
    ),
    Sign(
        term="mother",
        description="Tap the thumb of an open five-hand on your chin.",
        aliases=("mom", "mum", "mummy", "mommy"),
    ),
    Sign(
        term="father",
        description="Tap the thumb of an open five-hand on your forehead.",
        aliases=("dad", "daddy", "papa"),
    ),
    Sign(
        term="eat",
        description=(
            "Bring flattened fingertips and thumb to your mouth a couple of "
            "times, as though eating."
        ),
        aliases=("food", "hungry"),
    ),
    Sign(
        term="drink",
        description="Hold a C handshape at your mouth and tip it up, like a cup.",
        aliases=("thirsty",),
    ),
    Sign(
        term="water",
        description="Tap the index finger of a W handshape twice on your chin.",
    ),
    Sign(
        term="more",
        description="Bring flattened O handshapes together so the fingertips tap twice.",
    ),
    Sign(
        term="good",
        description=(
            "Touch the fingertips of a flat hand to your chin, then lower that "
            "hand onto the palm of the other."
        ),
        aliases=("well done", "fine"),
    ),
    Sign(
        term="bad",
        description=(
            "Touch the fingertips of a flat hand to your chin, then turn the hand "
            "over and move it down and away."
        ),
    ),
    Sign(
        term="happy",
        description=(
            "Brush flat hands upward in circles against your chest, with a happy "
            "face."
        ),
        aliases=("glad", "joy"),
    ),
    Sign(
        term="sad",
        description=(
            "Hold both open hands in front of your face and draw them slowly "
            "downward, with a downcast expression."
        ),
        aliases=("unhappy",),
    ),
    Sign(
        term="sorry to hear that",
        description=(
            "Sign SORRY (an A-hand circling on the chest) and nod gently; facial "
            "expression carries the sympathy."
        ),
    ),
    Sign(
        term="slow down",
        description=(
            "Draw one flat hand slowly up the back of the other hand from "
            "fingertips to wrist; a polite way to ask a signer to slow down."
        ),
        aliases=("slow", "please slow down"),
    ),
    Sign(
        term="again",
        description=(
            "Arc a bent hand over and into the flat palm of the other hand; also "
            "used to ask someone to repeat a sign."
        ),
        aliases=("repeat", "say that again"),
    ),
    Sign(
        term="stop",
        description="Chop the edge of a flat hand down onto the palm of the other hand.",
    ),
    Sign(
        term="wait",
        description=(
            "Hold both hands up, palms up and fingers apart, and wiggle the "
            "fingers."
        ),
    ),
    Sign(
        term="bathroom",
        description="Shake the T handshape (thumb between index and middle fingers) side to side.",
        aliases=("toilet", "restroom"),
    ),
    Sign(
        term="work",
        description="Tap the wrist of one fist on top of the wrist of the other fist twice.",
        aliases=("job",),
    ),
    Sign(
        term="school",
        description="Clap the flat palms of both hands together twice.",
    ),
    Sign(
        term="home",
        description=(
            "Touch flattened fingertips to the corner of your mouth and then to "
            "your cheek."
        ),
    ),
)


_STOPWORD_PREFIX = re.compile(r"^(?:the|a|an|to|for|in)\s+", re.IGNORECASE)
_TRAILING_FILLER = re.compile(
    r"\s+(?:in|using)\s+(?:asl|american sign language|sign language|signs?)$",
    re.IGNORECASE,
)


def _normalise(text: str) -> str:
    """Return a comparable form of ``text`` for lookups."""

    cleaned = (text or "").strip().lower()
    cleaned = re.sub(r"[^\w\s'-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = _TRAILING_FILLER.sub("", cleaned).strip()
    cleaned = _STOPWORD_PREFIX.sub("", cleaned)
    return cleaned.strip()


def _build_index(signs: Sequence[Sign]) -> Dict[str, Sign]:
    index: Dict[str, Sign] = {}
    for sign in signs:
        for key in sign.keys:
            index.setdefault(_normalise(key), sign)
    return index


_INDEX: Dict[str, Sign] = _build_index(SIGNS)


def terms() -> List[str]:
    """Return the known sign names, alphabetically."""

    return sorted(sign.term for sign in SIGNS)


def lookup(query: str) -> Optional[Sign]:
    """Return the sign matching ``query``, or ``None``.

    Matching ignores case and punctuation, understands aliases and tolerates
    small typos.
    """

    key = _normalise(query)
    if not key:
        return None
    sign = _INDEX.get(key)
    if sign is not None:
        return sign
    close = get_close_matches(key, list(_INDEX), n=1, cutoff=0.82)
    if close:
        return _INDEX[close[0]]
    return None


def suggestions(query: str, limit: int = 3) -> List[str]:
    """Return sign names that look similar to ``query``."""

    key = _normalise(query)
    if not key:
        return []
    matches = get_close_matches(key, list(_INDEX), n=limit * 2, cutoff=0.5)
    found: List[str] = []
    for match in matches:
        term = _INDEX[match].term
        if term not in found:
            found.append(term)
        if len(found) == limit:
            break
    return found


def letter(character: str) -> Optional[str]:
    """Return the handshape description for a single letter or digit."""

    key = (character or "").strip().upper()
    if len(key) != 1:
        return None
    return ALPHABET.get(key) or DIGITS.get(key)


def alphabet_lines() -> List[str]:
    """Return one description per letter of the manual alphabet."""

    return [f"{name}: {shape}" for name, shape in ALPHABET.items()]


def fingerspell(text: str, limit: int = 40) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Fingerspell ``text``.

    Returns the spelled characters paired with their handshape description and
    the list of characters that have no handshape in the manual alphabet.
    ``limit`` caps how many characters are described.
    """

    spelled: List[Tuple[str, str]] = []
    skipped: List[str] = []
    for character in (text or "").strip():
        if len(spelled) >= limit:
            break
        if character.isspace():
            if spelled and spelled[-1][0] != "␣":
                spelled.append(("␣", "pause briefly to mark a word break"))
            continue
        shape = letter(character)
        if shape is None:
            if character not in skipped:
                skipped.append(character)
            continue
        spelled.append((character.upper(), shape))
    while spelled and spelled[-1][0] == "␣":
        spelled.pop()
    return spelled, skipped
