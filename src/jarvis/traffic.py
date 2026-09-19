"""Offline knowledge about road traffic signs and signals used worldwide.

The data set is hand curated and dependency free. It covers the two families
of signage that most of the world follows — the Vienna Convention on Road
Signs and Signals (1968), used across Europe, much of Asia, Africa and South
America, and the Manual on Uniform Traffic Control Devices (MUTCD), used in
the United States and, with local variations, in Canada and Mexico — together
with the regional variations that travellers actually meet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class SignCategory:
    """A family of signs, described by its shape and colour language."""

    name: str
    shape: str
    colours: str
    meaning: str
    aliases: Sequence[str] = field(default_factory=tuple)

    @property
    def keys(self) -> Tuple[str, ...]:
        return (self.name, *self.aliases)


@dataclass(frozen=True)
class TrafficSign:
    """A single sign, with its shape, meaning and regional variations."""

    name: str
    category: str
    shape: str
    colours: str
    meaning: str
    regional: str = ""
    aliases: Sequence[str] = field(default_factory=tuple)

    @property
    def keys(self) -> Tuple[str, ...]:
        return (self.name, *self.aliases)


CATEGORIES: Tuple[SignCategory, ...] = (
    SignCategory(
        name="Warning signs",
        shape=(
            "equilateral triangle pointing up under the Vienna Convention; "
            "a diamond in the United States, Canada, Australia, New Zealand "
            "and Ireland"
        ),
        colours=(
            "white or yellow face with a red border (Vienna); black on yellow "
            "or fluorescent yellow-green (MUTCD)"
        ),
        meaning=(
            "Warn of a hazard ahead — a bend, a crossing, road works or "
            "animals — so that drivers slow down and prepare."
        ),
        aliases=("warning", "danger signs", "danger warning signs", "hazard signs"),
    ),
    SignCategory(
        name="Prohibitory signs",
        shape="circle, often with a diagonal red bar",
        colours="white or yellow face with a wide red ring",
        meaning=(
            "Forbid a manoeuvre: no entry, no overtaking, no parking, no "
            "U-turn, or a maximum speed, height or weight."
        ),
        aliases=("prohibition signs", "prohibitory", "restrictive signs", "red circle"),
    ),
    SignCategory(
        name="Mandatory signs",
        shape="circle",
        colours="blue face with white symbols",
        meaning=(
            "Order the movement the symbol shows — turn left, keep right, "
            "use the cycle track, obey a minimum speed."
        ),
        aliases=("mandatory", "blue circle", "obligation signs"),
    ),
    SignCategory(
        name="Priority signs",
        shape=(
            "distinct outlines so they read even when snow covered: an octagon "
            "for stop, a downward triangle for give way, a yellow diamond for "
            "a priority road"
        ),
        colours="red, white and yellow",
        meaning="Say who goes first where paths cross.",
        aliases=("priority", "right of way signs", "right-of-way"),
    ),
    SignCategory(
        name="Information signs",
        shape="rectangle or square",
        colours=(
            "blue or green panels for services and directions; brown for "
            "tourist and cultural destinations in most countries"
        ),
        meaning=(
            "Give guidance rather than orders: destinations, distances, "
            "parking, hospitals, fuel and rest areas."
        ),
        aliases=("information", "guide signs", "service signs", "direction signs"),
    ),
    SignCategory(
        name="Additional panels",
        shape="small rectangle mounted under another sign",
        colours="white with black text and symbols",
        meaning=(
            "Qualify the sign above: the distance to the hazard, the length "
            "of the restriction, the hours it applies or the vehicles it "
            "affects."
        ),
        aliases=("supplementary plates", "sub-plates", "additional plates"),
    ),
)


SIGNS: Tuple[TrafficSign, ...] = (
    TrafficSign(
        name="Stop",
        category="Priority signs",
        shape="regular octagon",
        colours="white legend or border on red",
        meaning=(
            "Come to a complete halt at the line, give way to all traffic and "
            "pedestrians, and only move off when the way is clear."
        ),
        regional=(
            "The octagon is near universal. Most countries keep the English "
            "word STOP; Japan uses a downward red triangle reading 止まれ, "
            "China and Israel use their own scripts, and Quebec signs read "
            "ARRÊT."
        ),
        aliases=("stop sign", "octagon sign", "halt"),
    ),
    TrafficSign(
        name="Give way",
        category="Priority signs",
        shape="equilateral triangle pointing down",
        colours="white face with a red border",
        meaning=(
            "Yield to traffic on the road you are joining or crossing; you "
            "may continue without stopping if the way is clear."
        ),
        regional=(
            "Called YIELD in the United States, Canada and Ireland, GIVE WAY "
            "in the United Kingdom, Australia and New Zealand, and left "
            "wordless across most of continental Europe."
        ),
        aliases=("yield", "yield sign", "give way sign", "inverted triangle"),
    ),
    TrafficSign(
        name="No entry",
        category="Prohibitory signs",
        shape="circle",
        colours="red disc with a horizontal white bar",
        meaning=(
            "Vehicles must not pass this point — usually the exit of a "
            "one-way street."
        ),
        regional=(
            "The red disc with a white bar is the Vienna standard; the MUTCD "
            "uses a white circle with a red ring and bar, or the black-on-"
            "white DO NOT ENTER and WRONG WAY signs."
        ),
        aliases=("do not enter", "wrong way", "no entry sign"),
    ),
    TrafficSign(
        name="Speed limit",
        category="Prohibitory signs",
        shape="circle",
        colours="white face, red ring, black numerals",
        meaning="The maximum legal speed from this sign until it is cancelled.",
        regional=(
            "Kilometres per hour almost everywhere; miles per hour in the "
            "United States, the United Kingdom and a handful of territories. "
            "US limits appear on a white rectangle reading SPEED LIMIT."
        ),
        aliases=("speed limit sign", "maximum speed", "speed restriction"),
    ),
    TrafficSign(
        name="End of speed limit",
        category="Prohibitory signs",
        shape="circle",
        colours="white or grey face with black diagonal slashes over the number",
        meaning="The posted limit ends and the general limit for the road applies.",
        regional=(
            "Common in Europe. A plain white circle with black slashes ends "
            "all previous restrictions."
        ),
        aliases=("derestriction", "end of restriction", "national speed limit"),
    ),
    TrafficSign(
        name="No overtaking",
        category="Prohibitory signs",
        shape="circle",
        colours="white face, red ring, two cars — the left one red",
        meaning="Overtaking other motor vehicles is forbidden on this stretch.",
        regional=(
            "The United States uses a yellow pennant on the left shoulder "
            "reading NO PASSING ZONE, plus a solid yellow centre line."
        ),
        aliases=("no passing", "overtaking prohibited", "no passing zone"),
    ),
    TrafficSign(
        name="No parking",
        category="Prohibitory signs",
        shape="circle",
        colours="blue face with a red ring and one red diagonal bar",
        meaning="Vehicles may not be left standing here.",
        regional=(
            "Two crossed red bars mean no stopping at all (a clearway). The "
            "MUTCD spells the rule out in words on a white rectangle."
        ),
        aliases=("parking prohibited", "no parking sign"),
    ),
    TrafficSign(
        name="No stopping",
        category="Prohibitory signs",
        shape="circle",
        colours="blue face with a red ring and two crossed red bars",
        meaning=(
            "You may not stop at all, even briefly, except in an emergency; "
            "known as a clearway."
        ),
        regional="Marked by red road edge lines in the United Kingdom.",
        aliases=("clearway", "no standing", "no stopping sign"),
    ),
    TrafficSign(
        name="No U-turn",
        category="Prohibitory signs",
        shape="circle",
        colours="white face, red ring, a black U-shaped arrow crossed out",
        meaning="Turning back in the opposite direction is forbidden here.",
        aliases=("u turn prohibited", "no u turn"),
    ),
    TrafficSign(
        name="No horn",
        category="Prohibitory signs",
        shape="circle",
        colours="white face, red ring, a black horn symbol",
        meaning="Sounding the horn is prohibited, usually near hospitals or at night.",
        regional=(
            "Widely posted in India, China and the Middle East, where horn "
            "use is otherwise common."
        ),
        aliases=("silence zone", "horn prohibited", "no honking"),
    ),
    TrafficSign(
        name="Height limit",
        category="Prohibitory signs",
        shape="circle",
        colours="white face, red ring, two arrows and a measurement",
        meaning=(
            "Vehicles taller than the figure shown may not pass — check "
            "bridges, tunnels and car park entrances."
        ),
        regional="Metres almost everywhere; feet and inches in the United States.",
        aliases=("low bridge", "maximum height", "clearance"),
    ),
    TrafficSign(
        name="Weight limit",
        category="Prohibitory signs",
        shape="circle",
        colours="white face, red ring, a figure in tonnes",
        meaning="Vehicles above the stated laden weight may not pass.",
        aliases=("maximum weight", "weight restriction", "axle limit"),
    ),
    TrafficSign(
        name="One way",
        category="Information signs",
        shape="rectangle",
        colours="blue panel with a white arrow, or a black-on-white arrow panel",
        meaning="Traffic may travel in the direction of the arrow only.",
        aliases=("one way street", "single direction"),
    ),
    TrafficSign(
        name="Roundabout",
        category="Mandatory signs",
        shape="circle",
        colours="blue face with three white arrows in a ring",
        meaning=(
            "A roundabout ahead: follow the arrows around the island. Traffic "
            "circulates anticlockwise where people drive on the right and "
            "clockwise where they drive on the left."
        ),
        regional=(
            "Entering traffic gives way to the roundabout in most of Europe "
            "and Australia; the United States uses a yellow warning diamond "
            "with a circular arrow plus YIELD signs on entry."
        ),
        aliases=("traffic circle", "rotary", "roundabout ahead"),
    ),
    TrafficSign(
        name="Keep right",
        category="Mandatory signs",
        shape="circle",
        colours="blue face with a white arrow",
        meaning="Pass the obstruction or island on the side the arrow points to.",
        regional="Mirrored as keep left in left-hand-drive-lane countries.",
        aliases=("keep left", "pass this side", "mandatory direction"),
    ),
    TrafficSign(
        name="Minimum speed",
        category="Mandatory signs",
        shape="circle",
        colours="blue face with white numerals",
        meaning="You must travel at least this fast unless conditions prevent it.",
        aliases=("minimum speed limit",),
    ),
    TrafficSign(
        name="Cycle track",
        category="Mandatory signs",
        shape="circle",
        colours="blue face with a white bicycle",
        meaning=(
            "A path reserved for cyclists, who must use it where the sign is "
            "mandatory."
        ),
        regional=(
            "A bicycle in a red ring instead forbids cycling; a green panel "
            "marks advisory cycle routes in North America."
        ),
        aliases=("bicycle lane", "bike lane", "cycle lane"),
    ),
    TrafficSign(
        name="Priority road",
        category="Priority signs",
        shape="square set on a corner (a diamond)",
        colours="yellow centre with a white border",
        meaning=(
            "You are on the priority road: traffic joining from side roads "
            "must give way until the sign is cancelled by a crossed-out copy."
        ),
        regional="Standard across Europe; not used in the United States.",
        aliases=("main road", "priority road sign"),
    ),
    TrafficSign(
        name="Priority to oncoming traffic",
        category="Priority signs",
        shape="circle",
        colours="white face, red ring, a red arrow and a black arrow",
        meaning=(
            "The road narrows and oncoming vehicles go first; wait until it "
            "is clear."
        ),
        regional=(
            "Its blue square counterpart, with the black arrow larger, gives "
            "you the priority instead."
        ),
        aliases=("give way to oncoming traffic", "narrow road priority"),
    ),
    TrafficSign(
        name="Pedestrian crossing",
        category="Warning signs",
        shape="triangle for the warning; blue square for the crossing itself",
        colours="red-bordered triangle, or a blue square with a white walking figure",
        meaning=(
            "People on foot cross here. Slow down and be ready to stop; at a "
            "marked crossing pedestrians have priority."
        ),
        regional=(
            "Britain adds flashing amber Belisha beacons at zebra crossings; "
            "the United States uses a fluorescent yellow-green pentagon-topped "
            "diamond."
        ),
        aliases=("zebra crossing", "crosswalk", "pedestrian crossing sign"),
    ),
    TrafficSign(
        name="School crossing",
        category="Warning signs",
        shape="triangle in Vienna countries; pentagon in the United States",
        colours="red-bordered triangle, or black on fluorescent yellow-green",
        meaning="Children are likely to be crossing; expect reduced speed limits.",
        regional=(
            "The five-sided school advance sign is a North American "
            "invention; Europe shows two children walking inside a triangle."
        ),
        aliases=("children crossing", "school zone", "school ahead"),
    ),
    TrafficSign(
        name="Level crossing",
        category="Warning signs",
        shape="triangle plus a St Andrew's cross at the crossing itself",
        colours="red and white",
        meaning=(
            "A railway crosses the road. Stop if lights flash or barriers "
            "fall, and never queue across the rails."
        ),
        regional=(
            "The crossbuck cross is worldwide; a fence symbol means barriers, "
            "a locomotive or a steam engine means an unguarded crossing."
        ),
        aliases=("railway crossing", "railroad crossing", "crossbuck", "grade crossing"),
    ),
    TrafficSign(
        name="Traffic signals ahead",
        category="Warning signs",
        shape="triangle or diamond",
        colours="red-bordered triangle, or black on yellow",
        meaning="Traffic lights are ahead, often hidden by a bend or a crest.",
        aliases=("signals ahead", "traffic lights ahead"),
    ),
    TrafficSign(
        name="Slippery road",
        category="Warning signs",
        shape="triangle or diamond",
        colours="a car with skid marks on a white or yellow face",
        meaning="The surface may be slippery when wet, icy or loose; brake gently.",
        aliases=("slippery when wet", "skid risk", "icy road"),
    ),
    TrafficSign(
        name="Road works",
        category="Warning signs",
        shape="triangle in Europe; diamond on orange in North America",
        colours="a digging figure, red-bordered white or black on orange",
        meaning="Construction or maintenance ahead: expect lane closures and workers.",
        regional=(
            "Orange is the standard work-zone colour in the United States, "
            "Canada and Australia; yellow is used in parts of Asia."
        ),
        aliases=("men at work", "construction ahead", "roadworks"),
    ),
    TrafficSign(
        name="Falling rocks",
        category="Warning signs",
        shape="triangle or diamond",
        colours="rocks tumbling from a slope",
        meaning="Rockfall or landslide risk; avoid stopping under the slope.",
        aliases=("rockfall", "landslide", "falling rock"),
    ),
    TrafficSign(
        name="Animal crossing",
        category="Warning signs",
        shape="triangle or diamond",
        colours="an animal silhouette",
        meaning=(
            "Animals may be on the road, especially at dawn and dusk; a "
            "collision at speed is dangerous for everyone."
        ),
        regional=(
            "The silhouette is local: deer across Europe and North America, "
            "moose in Scandinavia and Canada, kangaroos and wombats in "
            "Australia, camels in the Gulf, elephants in parts of Africa and "
            "Asia, penguins in New Zealand and South Africa, polar bears in "
            "Svalbard and northern Canada."
        ),
        aliases=("wild animals", "deer crossing", "kangaroo sign", "cattle crossing"),
    ),
    TrafficSign(
        name="Dangerous bend",
        category="Warning signs",
        shape="triangle or diamond",
        colours="a curved black arrow",
        meaning="A sharp or successive curve ahead; slow before you enter it.",
        regional=(
            "Often paired with a chevron board or a recommended speed plate."
        ),
        aliases=("sharp bend", "curve ahead", "hairpin"),
    ),
    TrafficSign(
        name="Steep hill",
        category="Warning signs",
        shape="triangle or diamond",
        colours="a sloping road with a gradient percentage",
        meaning=(
            "A steep descent or climb; descending vehicles should select a "
            "low gear and avoid riding the brakes."
        ),
        aliases=("steep descent", "steep grade", "gradient"),
    ),
    TrafficSign(
        name="Motorway",
        category="Information signs",
        shape="rectangle",
        colours=(
            "blue in most of Europe and Asia, green in Italy, Switzerland, "
            "Spain's toll roads and North America"
        ),
        meaning=(
            "Motorway rules begin: no pedestrians, cyclists, mopeds or slow "
            "vehicles, and a higher speed limit."
        ),
        regional=(
            "United States interstates use a red-and-blue shield; Germany's "
            "Autobahn sign is a blue bridge symbol."
        ),
        aliases=("freeway", "expressway", "autobahn", "highway sign", "interstate"),
    ),
    TrafficSign(
        name="Dead end",
        category="Information signs",
        shape="square",
        colours="blue with a white T-shaped bar in red",
        meaning="The road has no through route; you will have to come back.",
        regional="Signed NO THROUGH ROAD or DEAD END in English-speaking countries.",
        aliases=("no through road", "cul de sac"),
    ),
    TrafficSign(
        name="Hospital",
        category="Information signs",
        shape="square",
        colours="blue with a white H, or a bed and cross symbol",
        meaning="Directions to a hospital with emergency facilities; keep noise down.",
        aliases=("emergency room", "first aid", "hospital sign"),
    ),
    TrafficSign(
        name="Tourist destination",
        category="Information signs",
        shape="rectangle",
        colours="brown with white lettering or symbols",
        meaning="Directions to cultural, historic or scenic attractions.",
        regional=(
            "Brown tourist signing is used in the United Kingdom, the United "
            "States, France, Australia and many other countries."
        ),
        aliases=("brown sign", "tourist sign", "attraction sign"),
    ),
)


TRAFFIC_LIGHTS = (
    "Traffic lights run red on top, amber in the middle and green at the "
    "bottom (or red on the left in horizontal signals) so that colour-blind "
    "drivers can read them by position. Red means stop, green means go if the "
    "way is clear, and steady amber means stop unless you are too close to do "
    "so safely. A red-and-amber phase warns of green in Britain and Germany, "
    "a flashing amber means proceed with caution worldwide, and a flashing "
    "red is treated as a stop sign in North America. Green arrows permit a "
    "filtered turn; many countries add a countdown or a separate pedestrian "
    "and cycle signal."
)


_CONVENTIONS: Tuple[Tuple[str, str], ...] = (
    (
        "Vienna Convention",
        "The Vienna Convention on Road Signs and Signals (1968) standardises "
        "symbol-based signs: triangles warn, red circles forbid, blue circles "
        "instruct and rectangles inform. More than 80 countries across Europe, "
        "Asia, Africa and South America follow it, which is why signs are "
        "readable without knowing the language.",
    ),
    (
        "MUTCD",
        "The Manual on Uniform Traffic Control Devices governs the United "
        "States, and in adapted form Canada and Mexico. It leans on words and "
        "on shape and colour coding: octagon for stop, downward triangle for "
        "yield, diamond for warnings, pentagon for schools, yellow for "
        "hazards, orange for work zones, green for guidance and brown for "
        "recreation.",
    ),
    (
        "SADC-RTSM",
        "Southern African countries use the SADC Road Traffic Signs Manual, a "
        "blend of Vienna symbols with some North American shapes and "
        "bilingual wording.",
    ),
)

CONVENTIONS: Dict[str, str] = dict(_CONVENTIONS)


_STOPWORD_PREFIX = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)
_SUFFIXES = (" sign", " signs", " symbol", " symbols", " signal", " signals")


def _normalise(text: str) -> str:
    """Return a comparable lookup key for ``text``."""

    cleaned = (text or "").strip().lower()
    cleaned = re.sub(r"[^\w\s'-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = _STOPWORD_PREFIX.sub("", cleaned)
    return cleaned


def _strip_suffix(key: str) -> str:
    for suffix in _SUFFIXES:
        if key.endswith(suffix) and len(key) > len(suffix):
            return key[: -len(suffix)].strip()
    return key


def _build_index() -> Dict[str, TrafficSign]:
    index: Dict[str, TrafficSign] = {}
    for sign in SIGNS:
        for key in sign.keys:
            normalised = _normalise(key)
            index.setdefault(normalised, sign)
            index.setdefault(_strip_suffix(normalised), sign)
    return index


def _build_category_index() -> Dict[str, SignCategory]:
    index: Dict[str, SignCategory] = {}
    for category in CATEGORIES:
        for key in category.keys:
            normalised = _normalise(key)
            index.setdefault(normalised, category)
            index.setdefault(_strip_suffix(normalised), category)
    return index


_SIGN_INDEX: Dict[str, TrafficSign] = _build_index()
_CATEGORY_INDEX: Dict[str, SignCategory] = _build_category_index()


def sign_names() -> List[str]:
    """Return every known sign name, alphabetically."""

    return sorted(sign.name for sign in SIGNS)


def find_sign(query: str) -> Optional[TrafficSign]:
    """Return the sign matching ``query``, tolerating aliases and typos."""

    key = _normalise(query)
    if not key:
        return None
    for candidate in (key, _strip_suffix(key)):
        sign = _SIGN_INDEX.get(candidate)
        if sign is not None:
            return sign
    close = get_close_matches(_strip_suffix(key), list(_SIGN_INDEX), n=1, cutoff=0.82)
    if close:
        return _SIGN_INDEX[close[0]]
    return None


def find_category(query: str) -> Optional[SignCategory]:
    """Return the sign family matching ``query``."""

    key = _normalise(query)
    if not key:
        return None
    for candidate in (key, _strip_suffix(key)):
        category = _CATEGORY_INDEX.get(candidate)
        if category is not None:
            return category
    return None


def signs_in(category: str) -> List[TrafficSign]:
    """Return the signs belonging to ``category``, sorted by name."""

    found = find_category(category)
    if found is None:
        return []
    return sorted(
        (sign for sign in SIGNS if sign.category == found.name),
        key=lambda sign: sign.name,
    )


def find_convention(query: str) -> Optional[str]:
    """Return the description of a signing convention named in ``query``."""

    key = _normalise(query)
    if not key:
        return None
    if "vienna" in key:
        return CONVENTIONS["Vienna Convention"]
    if "mutcd" in key or "united states" in key or "american" in key:
        return CONVENTIONS["MUTCD"]
    if "sadc" in key or "southern africa" in key:
        return CONVENTIONS["SADC-RTSM"]
    return None


def describe_sign(sign: TrafficSign) -> str:
    """Return a readable paragraph about ``sign``."""

    parts = [
        f"{sign.name}: {sign.meaning}",
        f"It is a {sign.category.lower().rstrip('s')} — {sign.shape}, {sign.colours}.",
    ]
    if sign.regional:
        parts.append(sign.regional)
    return " ".join(parts)


def describe_category(category: SignCategory) -> str:
    """Return a readable paragraph about a family of signs."""

    return (
        f"{category.name}: {category.meaning} Shape: {category.shape}. "
        f"Colours: {category.colours}."
    )


def suggestions(query: str, limit: int = 3) -> List[str]:
    """Return sign names that look similar to ``query``."""

    key = _strip_suffix(_normalise(query))
    if not key:
        return []
    matches = get_close_matches(key, list(_SIGN_INDEX), n=limit * 3, cutoff=0.5)
    names: List[str] = []
    for match in matches:
        name = _SIGN_INDEX[match].name
        if name not in names:
            names.append(name)
        if len(names) == limit:
            break
    return names
