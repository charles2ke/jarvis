"""An offline reference for the Global Maritime Distress and Safety System.

The knowledge base follows the same shape as :mod:`jarvis.encyclopedia`:
entries are plain data, looked up by title or alias, with a forgiving
fallback so small typos still resolve.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Entry:
    """A single GMDSS reference entry."""

    title: str
    summary: str
    aliases: Sequence[str] = field(default_factory=tuple)

    @property
    def keys(self) -> Tuple[str, ...]:
        return (self.title, *self.aliases)


ENTRIES: Tuple[Entry, ...] = (
    Entry(
        title="GMDSS",
        summary=(
            "The Global Maritime Distress and Safety System is the worldwide "
            "set of radio procedures, equipment and shore services that carry "
            "a ship's distress alert to rescue authorities. It was introduced "
            "by the 1988 amendments to the SOLAS convention and became fully "
            "effective on 1 February 1999, replacing manual Morse watchkeeping "
            "with automatic alerting by satellite and digital selective "
            "calling."
        ),
        aliases=(
            "global maritime distress and safety system",
            "gmdss system",
            "g.m.d.s.s.",
        ),
    ),
    Entry(
        title="Sea areas",
        summary=(
            "GMDSS carriage requirements depend on where a ship trades. Area A1 "
            "is within VHF range of a coast station with DSC watch (roughly 20 "
            "to 30 nautical miles), A2 within MF DSC range (about 100 to 150 "
            "nautical miles), A3 within the footprint of a recognised "
            "geostationary satellite service (broadly 76 degrees north to 76 "
            "degrees south), and A4 is everything else, in practice the polar "
            "regions, where HF is the primary link."
        ),
        aliases=(
            "sea area",
            "gmdss sea areas",
            "a1",
            "a2",
            "a3",
            "a4",
            "area a1",
            "area a2",
            "area a3",
            "area a4",
        ),
    ),
    Entry(
        title="DSC",
        summary=(
            "Digital selective calling sends a short digital alert on dedicated "
            "VHF, MF and HF channels — VHF channel 70, 2187.5 kHz on MF and "
            "eight HF frequencies. A distress alert carries the ship's nine "
            "digit MMSI, its position and time, and optionally the nature of "
            "distress, so a receiving station knows who is in trouble and where "
            "before any voice contact is made."
        ),
        aliases=("digital selective calling", "dsc alert", "channel 70"),
    ),
    Entry(
        title="EPIRB",
        summary=(
            "An emergency position indicating radio beacon transmits on 406 MHz "
            "to the Cospas-Sarsat satellite system, with a 121.5 MHz homing "
            "signal for rescuers on scene. It is fitted in a float-free bracket "
            "with a hydrostatic release so it surfaces and activates by itself "
            "if the ship founders, identifying the vessel from its coded MMSI "
            "and, on GNSS-equipped models, reporting position to within metres."
        ),
        aliases=(
            "emergency position indicating radio beacon",
            "emergency position-indicating radio beacon",
            "epirbs",
            "406 mhz beacon",
        ),
    ),
    Entry(
        title="SART",
        summary=(
            "A search and rescue transponder is carried in survival craft and "
            "responds to a 9 GHz (X-band) radar pulse with a line of twelve "
            "blips on the searching ship's radar screen, marking the bearing "
            "and range of the survivors from up to about eight nautical miles. "
            "AIS-SART is the alternative, broadcasting GPS position as AIS "
            "target reports instead."
        ),
        aliases=(
            "search and rescue transponder",
            "search and rescue radar transponder",
            "ais-sart",
            "ais sart",
        ),
    ),
    Entry(
        title="NAVTEX",
        summary=(
            "NAVTEX broadcasts navigational warnings, meteorological warnings "
            "and forecasts, and urgent safety information as narrow-band "
            "direct-printing text on 518 kHz in English, with national services "
            "on 490 and 4209.5 kHz. Reception is automatic and unattended, and "
            "distress and navigational warning messages cannot be rejected by "
            "the receiver."
        ),
        aliases=("navtex receiver", "518 khz"),
    ),
    Entry(
        title="Inmarsat",
        summary=(
            "Inmarsat provides the geostationary satellite leg of GMDSS, "
            "covering sea area A3 with ship earth stations that carry distress "
            "priority calls, distress alerts and Enhanced Group Call traffic "
            "such as SafetyNET. Iridium was recognised as a second GMDSS "
            "satellite provider in 2020, extending satellite service into sea "
            "area A4."
        ),
        aliases=("inmarsat c", "safetynet", "enhanced group call", "iridium"),
    ),
    Entry(
        title="MMSI",
        summary=(
            "A maritime mobile service identity is the nine digit number that "
            "identifies a ship, coast station or group in DSC and AIS traffic. "
            "The first three digits are the maritime identification digits of "
            "the flag state, so a rescue coordination centre can tell at a "
            "glance which administration holds the vessel's registration "
            "details."
        ),
        aliases=("maritime mobile service identity",),
    ),
    Entry(
        title="Distress priorities",
        summary=(
            "Radio traffic has three safety priorities, highest first. Mayday "
            "signals grave and imminent danger to a vessel or person and "
            "demands immediate assistance. Pan-pan signals urgency — a serious "
            "situation that is not yet life threatening. Securite signals a "
            "safety message, typically a navigational or meteorological "
            "warning. Each spoken word is repeated three times."
        ),
        aliases=(
            "mayday",
            "pan pan",
            "pan-pan",
            "securite",
            "securite call",
            "distress priority",
            "urgency signal",
            "safety signal",
        ),
    ),
    Entry(
        title="SOS",
        summary=(
            "SOS is the Morse distress signal, three dots, three dashes and "
            "three dots sent as one unbroken character. It was agreed at the "
            "1906 Berlin radiotelegraph convention, took effect in 1908 and "
            "replaced the earlier Marconi call CQD; it is not an abbreviation "
            "of anything. Titanic transmitted both CQD and SOS in 1912, and "
            "Morse distress watchkeeping ended when GMDSS took over in 1999."
        ),
        aliases=("sos signal", "cqd", "morse distress signal"),
    ),
    Entry(
        title="Distress alert procedure",
        summary=(
            "Send the DSC distress alert first: press and hold the distress "
            "button, adding the nature of distress and a manual position if "
            "the set is not fed by GNSS. Then make the voice call on the "
            "matching distress frequency — VHF channel 16 or 2182 kHz — as "
            "'MAYDAY' three times, the ship's name and MMSI, position, nature "
            "of distress, assistance required and number of people on board. "
            "A false alert must never be switched off silently: report and "
            "cancel it on the same channel."
        ),
        aliases=(
            "distress alert",
            "sending a distress alert",
            "mayday call",
            "false alert",
            "channel 16",
            "2182 khz",
        ),
    ),
    Entry(
        title="GMDSS functional requirements",
        summary=(
            "SOLAS chapter IV requires every ship to perform nine functions: "
            "transmit ship-to-shore distress alerts by two independent means, "
            "receive shore-to-ship distress alerts, transmit and receive "
            "ship-to-ship distress alerts, transmit and receive search and "
            "rescue coordination traffic, transmit and receive on-scene "
            "communications, transmit and receive locating signals, receive "
            "maritime safety information, transmit and receive general "
            "radiocommunications, and exchange bridge-to-bridge "
            "communications."
        ),
        aliases=(
            "functional requirements",
            "solas chapter iv",
            "nine functions",
            "gmdss requirements",
        ),
    ),
)


_STOPWORD_PREFIX = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)


def _normalise(text: str) -> str:
    """Return a comparable form of ``text`` for lookups."""

    cleaned = text.strip().lower()
    cleaned = re.sub(r"[^\w\s'-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = _STOPWORD_PREFIX.sub("", cleaned)
    cleaned = re.sub(
        r"\b(?:[a-z]\s+)+[a-z]\b",
        lambda match: match.group().replace(" ", ""),
        cleaned,
    )
    return cleaned


def _build_index(entries: Sequence[Entry]) -> Dict[str, Entry]:
    index: Dict[str, Entry] = {}
    for entry in entries:
        for key in entry.keys:
            index.setdefault(_normalise(key), entry)
    return index


_INDEX: Dict[str, Entry] = _build_index(ENTRIES)


def topics() -> List[str]:
    """Return the entry titles, alphabetically."""

    return sorted(entry.title for entry in ENTRIES)


def lookup(query: str) -> Optional[Entry]:
    """Return the entry matching ``query``, or ``None``.

    Matching ignores case and punctuation, understands aliases, and falls
    back to close matches so small typos still resolve.
    """

    key = _normalise(query or "")
    if not key:
        return None
    entry = _INDEX.get(key)
    if entry is not None:
        return entry
    if key.endswith("s") and len(key) > 3:
        entry = _INDEX.get(key[:-1])
        if entry is not None:
            return entry
    close = get_close_matches(key, list(_INDEX), n=1, cutoff=0.82)
    if close:
        return _INDEX[close[0]]
    return None


def suggestions(query: str, limit: int = 3) -> List[str]:
    """Return titles that look similar to ``query``."""

    key = _normalise(query or "")
    if not key:
        return []
    matches = get_close_matches(key, list(_INDEX), n=limit * 2, cutoff=0.5)
    titles: List[str] = []
    for match in matches:
        title = _INDEX[match].title
        if title not in titles:
            titles.append(title)
        if len(titles) == limit:
            break
    return titles
