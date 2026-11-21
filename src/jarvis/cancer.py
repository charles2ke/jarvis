"""Curated cancer information from beat-it, available offline.

beat-it (https://charles2ke.github.io/beat-it/, source at
https://github.com/charles2ke/beat-it) is the user's own cancer information
site. :mod:`jarvis.cancer_data` is generated from its
``site/data/cancers.json``, ``site/data/faq.json`` and
``site/data/facts.json`` at commit 647f8d154681 (AGPL-3.0; the package
metadata says AGPL-3.0-only) by ``scripts/import_beat_it.py``. The daily
``updates.json`` feed (research, trials and news) and each entry's search
``query`` are not ported.

:func:`answer` turns a question into a short plain-text reply: an overview of
one of 22 cancer types, one part of it (symptoms, risk factors, screening,
treatments, medicines or recent FDA approvals), one of beat-it's FAQs or its
worldwide figures. It returns ``None`` when the text is not about cancer in
people — the star sign, the Tropic of Cancer, "a cancer on society" — so the
caller can fall back to something else.

Nothing here is medical advice, and Jarvis never diagnoses. Questions about
someone's own symptoms get a gentle "please see a doctor" reply, people who
say that they or someone close to them has cancer get a kind acknowledgement
first, and every reply ends with a disclaimer and a credit line. The data is
a snapshot, so replies say when beat-it last reviewed it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import get_close_matches
from typing import Dict, List, Optional, Sequence, Tuple

from jarvis.cancer_data import CANCERS as _RAW_CANCERS
from jarvis.cancer_data import FACTS as _RAW_FACTS
from jarvis.cancer_data import FAQS as _RAW_FAQS
from jarvis.dates import MONTH_NAMES

PROJECT = "beat-it"
SITE_URL = "https://charles2ke.github.io/beat-it/"
REPO_URL = "https://github.com/charles2ke/beat-it"
CREDIT = f"From {PROJECT}: {SITE_URL}"
DISCLAIMER = (
    "General information, not medical advice or a diagnosis — talk to a "
    "doctor about your own situation."
)

# beat-it's own wording, from its type pages.
TREATMENT_NOTE = (
    "Treatment depends on the cancer's type, stage, biomarkers and the "
    "individual."
)
MEDICINES_NOTE = (
    "Examples of approved medicines, not a complete list or a recommendation. "
    "Eligibility depends on stage, biomarkers and prior treatment."
)


@dataclass(frozen=True)
class Link:
    """A named source, such as the body behind a screening recommendation."""

    name: str
    url: str


@dataclass(frozen=True)
class Medicine:
    """An example medicine; ``since`` is the date of a new FDA approval."""

    name: str
    use: str
    since: Optional[str] = None


@dataclass(frozen=True)
class Approval:
    """An FDA oncology approval as beat-it lists it."""

    date: str
    drug: str
    text: str
    url: str


@dataclass(frozen=True)
class Cancer:
    """One cancer type as beat-it describes it."""

    id: str
    name: str
    group: str
    aliases: Tuple[str, ...]
    nci: str
    summary: str
    symptoms: Tuple[str, ...]
    risk_factors: Tuple[str, ...]
    screening: str
    screening_source: Optional[Link]
    treatments: Tuple[str, ...]
    medicines: Tuple[Medicine, ...]
    approvals: Tuple[Approval, ...]  # newest first
    reviewed: str

    @property
    def short(self) -> str:
        """The name to suggest in follow-up requests, e.g. ``lung cancer``."""

        return _SHORT_NAMES.get(self.id) or _strip_parenthetical(self.name).lower()

    @property
    def label(self) -> str:
        """The name in running text, e.g. ``skin cancer (melanoma)``."""

        return self.name[:1].lower() + self.name[1:]


@dataclass(frozen=True)
class Faq:
    """One of beat-it's frequently asked questions."""

    question: str
    answer: str
    link: str


@dataclass(frozen=True)
class Fact:
    """A worldwide figure with its source."""

    value: str
    label: str
    source: str
    url: str


_SHORT_NAMES: Dict[str, str] = {"brain": "brain tumor", "childhood": "childhood cancer"}


def _strip_parenthetical(name: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", name).strip()


def _cancer(raw: Dict) -> Cancer:
    source = raw["screening_source"]
    approvals = sorted(
        (Approval(**approval) for approval in raw["approvals"]),
        key=lambda approval: approval.date,
        reverse=True,
    )
    return Cancer(
        id=raw["id"],
        name=raw["name"],
        group=raw["group"],
        aliases=tuple(raw["aliases"]),
        nci=raw["nci"],
        summary=raw["summary"],
        symptoms=tuple(raw["symptoms"]),
        risk_factors=tuple(raw["risk_factors"]),
        screening=raw["screening"],
        screening_source=Link(source["name"], source["url"]) if source else None,
        treatments=tuple(raw["treatments"]),
        medicines=tuple(
            Medicine(item["name"], item["use"], item["since"]) for item in raw["medicines"]
        ),
        approvals=tuple(approvals),
        reviewed=raw["reviewed"],
    )


CANCERS: Tuple[Cancer, ...] = tuple(_cancer(raw) for raw in _RAW_CANCERS)
FAQS: Tuple[Faq, ...] = tuple(Faq(raw["q"], raw["a"], raw["link"]) for raw in _RAW_FAQS)
FACTS_TITLE: str = _RAW_FACTS["title"]
FACTS_INTRO: str = _RAW_FACTS["intro"]
FACTS: Tuple[Fact, ...] = tuple(
    Fact(raw["value"], raw["label"], raw["source"], raw["url"]) for raw in _RAW_FACTS["facts"]
)

#: Entry display names, in beat-it's order, for the site topic index.
NAMES: Tuple[str, ...] = tuple(cancer.name for cancer in CANCERS)
#: The latest date beat-it reviewed an entry (ISO format).
REVIEWED: str = max(cancer.reviewed for cancer in CANCERS)

_FAQ_BY_QUESTION: Dict[str, Faq] = {faq.question: faq for faq in FAQS}


def _date(iso: str) -> str:
    """Return ``12 November 2026`` for ``2026-11-12``."""

    year, month, day = (int(part) for part in iso.split("-"))
    return f"{day} {MONTH_NAMES[month]} {year}"


def _months_between(earlier: str, later: str) -> int:
    first = [int(part) for part in earlier.split("-")]
    second = [int(part) for part in later.split("-")]
    months = (second[0] - first[0]) * 12 + second[1] - first[1]
    return months - (1 if second[2] < first[2] else 0)


# ---------------------------------------------------------------- normalising

# beat-it's own British-to-US folding, so "tumour" finds "tumor".
_SPELLINGS = tuple(
    (re.compile(pattern), replacement)
    for pattern, replacement in (
        (r"tumour", "tumor"),
        (r"leukaem", "leukem"),
        (r"oesophag", "esophag"),
        (r"paediatr", "pediatr"),
        (r"haem", "hem"),
        (r"anaem", "anem"),
        (r"oestr", "estr"),
        (r"foetal", "fetal"),
    )
)

_CONTRACTIONS = tuple(
    (re.compile(pattern), replacement)
    for pattern, replacement in (
        (r"\b(he|she|it|that|who)'s got\b", r"\1 has got"),
        (r"\b(i|you|we|they)'ve\b", r"\1 have"),
        (r"\b(?:i'm|im)\b", "i am"),
        (r"\bive\b", "i have"),
        (r"\bi'd\b", "i would"),
        (r"\bi'll\b", "i will"),
        (r"\b(it|that|this|he|she|what|there|who|where|how)'s\b", r"\1 is"),
        (r"\bwhats\b", "what is"),
        (r"\b(you|we|they)'re\b", r"\1 are"),
        (r"\bcan'?t\b", "cannot"),
        (r"\bwon'?t\b", "will not"),
        (r"\b(do|does|did|is|are|was|were|have|has|had|could|would|should)n'?t\b", r"\1 not"),
    )
)

_DISEASE_WORDS = (
    r"cancers?|cancerous|tumors?|carcinomas?|adenocarcinomas?|neoplasms?|metasta\w*"
    r"|leukemias?|lymphomas?|myelomas?|melanomas?|sarcomas?|osteosarcomas?|glioblastomas?"
    r"|gliomas?|astrocytomas?|meningiomas?|neuroblastomas?|retinoblastomas?|mesotheliomas?"
    r"|cholangiocarcinomas?|hodgkin'?s disease"
    r"|malignan(?:t|cy|cies)(?!\s+(?:narcissis\w*|hypertherm\w*|hypertension|otitis|malaria)\b)"
)
# Acronyms that only ever mean a cancer. GIST is handled separately because
# "gist" is an ordinary word; NHL and ALL are left out for the same reason.
_ACRONYMS = r"aml|cml|cll|nsclc|sclc|dcis|tnbc|gbm|hcc|rcc|dlbcl|pdac|mcrpc"
_DISEASE = rf"(?:{_DISEASE_WORDS}|{_ACRONYMS})"
_CHEMO = r"chemo(?:s|therap\w*|radi\w*|immunotherap\w*|embolization)?"
_TREATMENT = (
    rf"(?:{_CHEMO}|radiotherapy|radiation therapy|oncolog\w*|carcinogen\w*"
    r"|targeted therap\w*|immunotherap\w*)"
)
_CONTEXT_RE = re.compile(rf"\b(?:{_DISEASE}|{_TREATMENT})\b")
_WORD_CONTEXT_RE = re.compile(rf"\b(?:{_DISEASE_WORDS}|{_TREATMENT})\b")
_DISEASE_ONLY_RE = re.compile(rf"(?:{_DISEASE})")
_GIST_RE = re.compile(r"\bGISTs?\b")
_GIST_OF_RE = re.compile(r"\bthe gist of\b|\bgist of (?:it|this|that|what)\b")
# The same letters elsewhere: AML checks (anti-money laundering), a club's GBM
# (general body meeting), HCC codes (insurance billing), RCC slabs (concrete).
_ACRONYM_ELSEWHERE_RE = re.compile(
    r"\b(?:kyc|money laundering|aml (?:and|or) kyc)\b"
    r"|\baml (?:compliance|checks?|polic(?:y|ies)|rules?|regulations?|officers?|programs?"
    r"|programmes?|training|audits?|risk assessments?|procedures?|requirements?|laws?"
    r"|directives?|screening)\b"
    r"|\bgbm (?:meetings?|agenda|minutes|notice|elections?|votes?|motions?)\b"
    r"|\b(?:annual|club's|club|society|union|association|association's) gbm\b"
    r"|\bhcc (?:cod\w*|categor\w*|billing|risk scores?|risk adjustment|capture|recapture"
    r"|documentation|gaps?)\b"
    r"|\brcc (?:slabs?|beams?|columns?|footings?|walls?|structures?|frames?|design|roads?"
    r"|pipes?|buildings?)\b"
)

# A disease word that names a job, place or event rather than an illness.
_NOT_PERSONAL = (
    r"(?!\s+(?:research\w*|doctors?|nurses?|specialists?|surgeons?|scientists?|charit(?:y|ies)"
    r"|cent(?:er|re)s?|hospitals?|wards?|units?|clinics?|awareness|fundrais\w*|walks?|runs?"
    r"|events?|societ(?:y|ies)|institutes?|trusts?|foundations?|biolog\w*)\b)"
)
_D = rf"\b{_DISEASE}\b{_NOT_PERSONAL}"

_FUZZY_NAMES = (
    "leukemia",
    "lymphoma",
    "myeloma",
    "melanoma",
    "sarcoma",
    "osteosarcoma",
    "glioblastoma",
    "glioma",
    "astrocytoma",
    "meningioma",
    "neuroblastoma",
    "retinoblastoma",
    "mesothelioma",
    "cholangiocarcinoma",
    "carcinoma",
    "adenocarcinoma",
)


def _normalise(text: str) -> str:
    """Lower-case ``text``, fold accents and spellings, and drop punctuation."""

    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch)).lower()
    folded = re.sub(r"[\u2018\u2019`]", "'", folded)
    for pattern, replacement in _SPELLINGS:
        folded = pattern.sub(replacement, folded)
    folded = re.sub(r"[^a-z0-9']+", " ", folded)
    folded = re.sub(r"(?<![a-z0-9])'+|'+(?![a-z0-9])", " ", folded)
    return re.sub(r"\s+", " ", folded).strip()


def _correct(word: str) -> str:
    """Fix a typo in a long disease name ("lukemia"); never touch "cancer"."""

    if len(word) < 6 or _DISEASE_ONLY_RE.fullmatch(word):
        return word
    close = get_close_matches(word, _FUZZY_NAMES, n=1, cutoff=0.85)
    return close[0] if close else word


def _prepare(text: str) -> str:
    """Return the comparable form of ``text`` used by every matcher here."""

    prepared = _normalise(text)
    for pattern, replacement in _CONTRACTIONS:
        prepared = pattern.sub(replacement, prepared)
    return " ".join(_correct(word) for word in prepared.split())


def _clauses(text: str) -> List[str]:
    parts = re.split(r"[.?!;:,\n()]+|\s[-\u2013\u2014]+\s|[\u2013\u2014]", text or "")
    return [clause for clause in (_prepare(part) for part in parts) if clause]


def _has_context(prepared: str, gist: bool) -> bool:
    if gist:
        return True
    if "allerg" in prepared:
        # Allergy immunotherapy is not about cancer.
        prepared = re.sub(r"\bimmunotherap\w*", " ", prepared)
    if not _CONTEXT_RE.search(prepared):
        return False
    return bool(_WORD_CONTEXT_RE.search(prepared)) or not _ACRONYM_ELSEWHERE_RE.search(prepared)


# ---------------------------------------------------------------- not medical

_ZODIAC = (
    r"aries|taurus|gemini|leo|virgo|libra|scorpio|sagittarius|capricorn|aquarius|pisces"
)
_SOCIETY = (
    r"society|democracy|politics|nation|country|humanity|civili[sz]ation|culture|government"
    r"|community|planet|team|club|game|sport|industry|internet|party|church|economy|system"
    r"|city|town|workplace|company|organi[sz]ation|soul|movement|republic"
)
_VICES = (
    r"corruption|racism|sexism|hate|hatred|greed|bigotry|crime|bureaucracy|violence|poverty"
    r"|populism|debt|envy|jealousy|resentment|gossip|lies|lying|cynicism|toxicity|nepotism"
    r"|apathy|extremism|terrorism|misinformation|disinformation|propaganda|fascism"
    r"|nationalism|consumerism|materialism|selfishness|ego|bitterness|negativity|inequality"
    r"|sectarianism|tribalism|fake news|social media"
)
_IDENTITY_OK = (
    r"patients?|survivors?|sufferers?|researchers?|research|doctors?|nurses?|specialists?"
    r"|warriors?|fighters?|thrivers?|carers?|caregivers?|free|scientists?|biologists?|charit\w*"
    r"|support|surgeons?|physicians?|counsel+ors?|navigators?|volunteers?|advocates?|awareness"
    r"|screening|ward|unit"
)
_NOT_MEDICAL_RE = re.compile(
    r"\btropic of cancer\b"
    r"|\b(?:horoscopes?|zodiac|astrolog\w*|(?:star|sun|moon|rising) signs?|birth charts?"
    r"|natal charts?|ascendant|constellations?)\b"
    r"|\bcancers? (?:season|moon|rising|sun sign|traits?|personalit\w*|compatib\w*|the crab"
    r"|crab)\b"
    r"|\b(?:sun|moon|rising|venus|mars|mercury) (?:sign )?(?:is |in )cancer\b"
    rf"|\bcancers? (?:and|vs|versus|with|or|x) (?:{_ZODIAC})s?\b"
    rf"|\b(?:{_ZODIAC})s? (?:and|vs|versus|with|or|x) cancers?\b"
    r"|(?:\b(?:i am|you are|he is|she is|they are|we are|my sign is|my star sign is"
    rf"|born under)|^(?:as|being) an?) (?:a |an )?cancers?\b(?!\s+(?:{_IDENTITY_OK})\b)"
    r"|\b(?:a|the|like a|like) cancer (?:on|upon|in|of|to|within|eating(?: away at)?"
    r"|at the heart of|destroying|rotting|spreading through) "
    rf"(?:(?:our|the|this|modern|today's|my|their|his|her) )?(?:{_SOCIETY})\b"
    rf"|\b(?:{_VICES}) (?:is|are|was|were|has become|have become|became|acts like|is like"
    r"|spreads like) (?:a |like a |the |like )?cancer\b"
    r"|\bspread(?:s|ing)? like (?:a )?cancer\b"
    r"|\b(?:game|team|meta|comments?|thread|chat|server|update|patch|lobby|fandom|traffic"
    r"|music|song|code|codebase) (?:is|was|are) (?:pure |absolute |literal |actual |total )?"
    r"cancer\b"
)

_PET_RE = re.compile(
    r"\b(?:my|our|the|a|his|her|their)\s+(?:[a-z]+\s+)?(?:dogs?|pupp(?:y|ies)|cats?|kittens?"
    r"|pets?|horses?|ponies|pony|rabbits?|bunny|hamsters?|ferrets?|guinea pigs?|parrots?"
    r"|budgies?)\b(?!\s+(?:ct\s+|mri\s+)?scans?\b)(?!\s+ct\b)"
    r"|\b(?:vets?|veterinar\w*|canine|feline|equine)\b"
    r"|\bin (?:dogs|cats|pets|animals|horses)\b"
)
_OWN_PET_RE = re.compile(
    r"\b(?:my|our)\s+(?:[a-z]+\s+)?(?P<pet>dog|puppy|cat|kitten|pet|horse|pony|rabbit|bunny"
    r"|hamster|ferret|guinea pig|parrot|budgie)\b"
)


# ---------------------------------------------------------------- entry lookup

# Extra names from beat-it's search synonyms. Organ words are "generic": they
# only pick an entry when the text is clearly about cancer.
_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "colorectal": ("bowel", "colon", "rectal", "rectum"),
    "stomach": ("gastric",),
    "uterine": ("womb", "uterus", "endometrial"),
    "cervical": ("cervix",),
    "ovarian": ("ovaries",),
    "pancreatic": ("pancreas",),
    "prostate": ("prostrate",),
    "esophageal": ("esophagus", "gullet"),
    "brain": ("spinal cord", "brain tumor", "spinal cord tumor"),
    "childhood": ("childhood cancer", "kids", "kid", "child", "children", "pediatric"),
}
_PERSON_KEYS = frozenset({"child", "children", "kid", "kids"})
_POSSESSIVE_BEFORE = re.compile(r"\b(?:my|our|your|his|her|their)\s+$")
_SPREAD_BEFORE = re.compile(
    r"\b(?:spread\w*|metasta\w*)\s+(?:to|into|in)\s+(?:(?:the|my|his|her|their|your)\s+)?$"
)


@dataclass(frozen=True)
class _Key:
    text: str
    cancer: Cancer
    specific: bool
    pattern: "re.Pattern[str]"


def _keys() -> Tuple[_Key, ...]:
    keys: List[_Key] = []
    for cancer in CANCERS:
        names = [cancer.name, _strip_parenthetical(cancer.name), cancer.id, *cancer.aliases]
        names += re.findall(r"\(([^)]*)\)", cancer.name)
        names += _SYNONYMS.get(cancer.id, ())
        seen = set()
        for name in names:
            text = _normalise(name)
            if not text or text in seen:
                continue
            seen.add(text)
            words = r"\s+".join(re.escape(word) for word in text.split())
            pattern = re.compile(rf"(?<![a-z0-9']){words}(?:'s|s|es)?(?![a-z0-9'])")
            keys.append(_Key(text, cancer, bool(_CONTEXT_RE.search(text)), pattern))
    return tuple(keys)


_KEYS = _keys()
_KEY_WORDS = sorted(
    {word for key in _KEYS for word in key.text.split() if not _DISEASE_ONLY_RE.fullmatch(word)},
    key=len,
    reverse=True,
)
_KEY_WORD_ALT = "|".join(re.escape(word) for word in _KEY_WORDS)


def _find_entry(prepared: str, *, context: bool, gist: bool) -> Optional[Cancer]:
    """Return the cancer type ``prepared`` is about, or ``None``.

    Names and specific aliases ("lung cancer", "NSCLC") always count; generic
    ones ("stomach", "HER2", "children") only count when the text is clearly
    about cancer. Ties go to specific keys, then the earliest, then the longest.
    """

    best: Optional[Tuple[int, int, int]] = None
    found: Optional[Cancer] = None
    for key in _KEYS:
        if key.text == "gist":
            if not gist:
                continue
            specific = True
        else:
            specific = key.specific
        if not specific and not context:
            continue
        for match in key.pattern.finditer(prepared):
            before = prepared[: match.start()]
            if not specific and key.text in _PERSON_KEYS and _POSSESSIVE_BEFORE.search(before):
                continue
            if not specific and _SPREAD_BEFORE.search(before):
                continue
            rank = (0 if specific else 1, match.start(), -len(key.text))
            if best is None or rank < best:
                best, found = rank, key.cancer
            break
    return found


# ---------------------------------------------------------------- people

_RELATIONS = (
    "mother in law",
    "father in law",
    "sister in law",
    "brother in law",
    "in laws",
    "mum",
    "mom",
    "mam",
    "mummy",
    "mommy",
    "mother",
    "dad",
    "daddy",
    "father",
    "parent",
    "parents",
    "stepmum",
    "stepmom",
    "stepmother",
    "stepdad",
    "stepfather",
    "brother",
    "brothers",
    "sister",
    "sisters",
    "sibling",
    "siblings",
    "son",
    "sons",
    "daughter",
    "daughters",
    "stepson",
    "stepdaughter",
    "child",
    "children",
    "kid",
    "kids",
    "baby",
    "toddler",
    "husband",
    "wife",
    "partner",
    "spouse",
    "fiance",
    "fiancee",
    "boyfriend",
    "girlfriend",
    "friend",
    "friends",
    "grandma",
    "grandmother",
    "granny",
    "gran",
    "nan",
    "nana",
    "nanna",
    "grandad",
    "granddad",
    "grandpa",
    "grandfather",
    "grandparent",
    "grandparents",
    "aunt",
    "auntie",
    "aunty",
    "uncle",
    "cousin",
    "niece",
    "nephew",
    "godmother",
    "godfather",
    "colleague",
    "coworker",
    "co worker",
    "boss",
    "neighbour",
    "neighbor",
    "teacher",
    "student",
    "flatmate",
    "roommate",
    "classmate",
    "family",
)
_PLURAL_RELATIONS = frozenset(
    {
        "in laws",
        "parents",
        "brothers",
        "sisters",
        "siblings",
        "sons",
        "daughters",
        "children",
        "kids",
        "friends",
        "grandparents",
    }
)
_CHILD_RELATIONS = frozenset({"child", "children", "kid", "kids", "baby", "toddler"})
_REL = "(?:" + "|".join(
    re.escape(name).replace(r"\ ", r"\s+") for name in sorted(_RELATIONS, key=len, reverse=True)
) + ")"
_MOD_WORDS = (
    r"best|close|older|younger|little|big|elder|baby|twin|step|ex|late|dear|beloved|lovely"
    r"|old|oldest|youngest|eldest|only|good|great|dearest|poor|sweet|whole"
)
_MODS = rf"(?:(?:{_MOD_WORDS})\s+){{0,2}}"
_HIDDEN_MODS = frozenset({"late", "dear", "beloved", "lovely", "dearest", "poor", "sweet"})
_MY_REL = rf"\b(?:my|our)\s+(?P<mods>{_MODS})(?P<rel>{_REL})(?:'s\s+(?P<rel2>{_REL}))?\b"
_MY_REL_RE = re.compile(_MY_REL)
# Object and possessive forms, for someone named only by a pronoun.
_PRONOUN_FORMS = {"he": ("him", "his"), "she": ("her", "her"), "they": ("them", "their")}
_PRONOUN_SUBJECTS = {"he": "he", "his": "he", "she": "she", "her": "she"}


@dataclass(frozen=True)
class _Person:
    """Who a message is about.

    ``name`` is ``None`` for the user, a relation such as ``mum`` or ``best
    friend``, or empty when only ``pronoun`` (or nothing) names them.
    """

    name: Optional[str] = None
    plural: bool = False
    late: bool = False
    pronoun: str = "they"

    @property
    def is_user(self) -> bool:
        return self.name is None

    @property
    def child(self) -> bool:
        return (self.name or "").split(" ")[-1] in _CHILD_RELATIONS

    @property
    def verb(self) -> str:
        """``are`` or ``is``, to agree with :meth:`subject`."""

        if self.is_user or self.plural or (not self.name and self.pronoun == "they"):
            return "are"
        return "is"

    def subject(self) -> str:
        if self.is_user:
            return "you"
        return f"your {self.name}" if self.name else self.pronoun

    def your(self) -> str:
        if self.is_user:
            return "you"
        return f"your {self.name}" if self.name else _PRONOUN_FORMS[self.pronoun][0]

    def possessive(self) -> str:
        if self.is_user:
            return "your"
        if not self.name:
            return _PRONOUN_FORMS[self.pronoun][1]
        return f"your {self.name}'" if self.name.endswith("s") else f"your {self.name}'s"


_YOU = _Person()


def _person(mods: str, rel: str, rel2: Optional[str] = None) -> _Person:
    words = mods.split()
    relations = []
    for relation in (rel, rel2):
        if relation:
            relation = re.sub(r"\s+", " ", relation)
            if relation in {"in laws", "co worker"}:
                relation = relation.replace(" ", "-")
            relations.append(relation)
    shown = " ".join(word for word in words if word not in _HIDDEN_MODS)
    joined = "'s ".join(relations)
    last = relations[-1].replace("-", " ")
    return _Person(
        name=f"{shown} {joined}".strip(), plural=last in _PLURAL_RELATIONS, late="late" in words
    )


def _match_person(match: "re.Match[str]") -> _Person:
    groups = match.groupdict()
    return _person(groups.get("mods") or "", groups["rel"], groups.get("rel2"))


def _first_relation(prepared: str) -> Optional[_Person]:
    match = _MY_REL_RE.search(prepared)
    return _match_person(match) if match else None


# ---------------------------------------------------------------- self-checks

_WORRY = (
    r"(?:worried|worry|worrying|scared|afraid|frightened|terrified|anxious|paranoid|concerned"
    r"|nervous|panick\w*|freaking out|fear\w*|petrified|stressed|stressing|obsess\w*)"
)
_THINK = (
    rf"(?:{_WORRY}|think|thinking|suspect\w*|convinced|pretty sure|sure|wonder\w*"
    r"|feel like|feeling like|feels like)"
)
_SYMPTOM_THING = (
    r"(?:lumps?|bumps?|moles?|spots?|freckles?|growths?|swelling|swollen \w+|lesions?|sores?"
    r"|ulcers?|rash(?:es)?|cough(?:ing)?|pains?|aches?|headaches?|bleeding|blood|bruis\w*"
    r"|discharge|nodes?|glands?|polyps?|cysts?|nodules?|mass(?:es)?|weight loss|lost weight"
    r"|losing weight|fatigue|tiredness|night sweats|fevers?|patch(?:es)?|changes?|itch\w*"
    r"|warts?|marks?|blemish\w*|hoarseness)"
)
_SYMPTOM_ANY = rf"(?:{_SYMPTOM_THING}|symptoms?|signs?)"
_GAP = (
    r"(?:be|been|mean|means|indicate|indicates|signal|signals|a|an|the|sign|signs|symptom"
    r"|symptoms|of|early|turn|turning|into|become|develop|developing|that|i|have|has|got"
    r"|possibly|actually|really|just|maybe|definitely|probably|some|lump|lumps|bump|mole"
    r"|moles|spot|spots|growth|swelling|cough|pain|rash|sore|bleeding|thing|benign|or|not"
    rf"|stage|\d+|{_KEY_WORD_ALT})"
)
_TRAIL = (
    r"(?:\s+(?:or|in|on|of|and|because|since|from|like|if|when|though|even|too|then|right"
    r"|already|again|yet|now|as well|related)\b.*)?$"
)
_WHO_REL = rf"my\s+(?P<mods>{_MODS})(?P<rel>{_REL})"
_FILLER = r"(?:\s+[a-z0-9']+)"

# Each pattern describes someone asking whether a symptom, or they, have cancer.
_SELF_CHECK_RES = tuple(
    re.compile(pattern)
    for pattern in (
        rf"\b(?:do|could|might|may|would) i (?:have|have got|got|be getting|be developing"
        rf"|be having)\b(?!\s+to\b){_FILLER}{{0,4}}?\s+{_D}",
        rf"\bam i (?:getting|developing|showing signs of)\b{_FILLER}{{0,3}}?\s+{_D}",
        rf"\bwhat if (?:it is|this is|that is|i have|i have got|i am getting|i got)\b"
        rf"{_FILLER}{{0,3}}?\s+{_D}",
        rf"(?:^|\s)(?:is|are|could|might|may|can|would|will|does|do)\s+(?:this|that|it|these"
        rf"|those)\s+(?:{_GAP}\s+){{0,6}}{_D}{_TRAIL}",
        rf"(?:^|\s)(?:it|this|that|they|these)\s+(?:might|could|may|must)\s+(?:be|mean"
        rf"|indicate)\b(?:\s+{_GAP})*?\s+{_D}{_TRAIL}",
        rf"\b(?:is|are|could|might|may|can|would|will|does|do)\s+(?P<who>my|his|her|their"
        rf"|this|that|these|those)\s+(?:[a-z0-9']+\s+){{0,2}}?{_SYMPTOM_ANY}\b"
        rf"{_FILLER}{{0,6}}?\s+{_D}",
        rf"\b(?:is|are|could|might|may|can|would|will|does|do)\s+the\s+(?:[a-z0-9']+\s+){{0,2}}?"
        rf"{_SYMPTOM_THING}\b{_FILLER}{{0,6}}?\s+{_D}",
        rf"\b{_THINK}\b(?:\s+(?:that|about|if|whether|like|maybe|really))*"
        rf"\s+(?P<who>i|it|this|that|he|she|they|{_WHO_REL})\s+(?:(?:might|may|could|must"
        r"|probably|really|actually|already|now|also|do|does|will|would)\s+)*(?:have|has|had"
        rf"|got|is|am|are|be|been|getting|developing|get)\b{_FILLER}{{0,5}}?\s+{_D}",
        rf"\bhow (?:do|would|can|could|will) i (?:know|tell|find out|check|be sure)\b"
        rf"(?:\s+(?:if|whether))?\s+i (?:have|have got|might have|got|had)\b{_FILLER}{{0,4}}?"
        rf"\s+{_D}",
        rf"\b(?:does|do|could|might|may|would)\s+(?P<who>he|she|they|{_WHO_REL})\s+(?:have"
        rf"|have got|got|be getting|be developing)\b(?!\s+to\b){_FILLER}{{0,4}}?\s+{_D}",
    )
)
# These need a disease word somewhere else in the message as well.
_SYMPTOM_STATEMENT_RES = tuple(
    re.compile(pattern)
    for pattern in (
        rf"\bi (?:found|noticed|felt|feel|have|have got|got|discovered|see|can see|can feel)"
        rf"\s+(?:[a-z0-9']+\s+){{0,3}}?{_SYMPTOM_THING}\b",
        r"\bi (?:have|have got|got|am having|am experiencing|experience|get|keep getting"
        r"|have had|had|am showing)\b(?:\s+(?!(?:read|heard|seen|learn\w*|stud\w*|questions?"
        r"|about|no|never|to)\b)[a-z0-9']+){0,5}?\s+(?:symptoms?|signs?)\b",
        r"\bmy symptoms\b",
    )
)
_RISK_WORDS_RE = re.compile(r"\b(?:risks?|chances?|odds|likely|likelihood)\b")


def _self_check(clauses: Sequence[str], prepared: str) -> Optional[_Person]:
    """Return who a "could this be cancer?" question is about, or ``None``."""

    risky = bool(_RISK_WORDS_RE.search(prepared))
    for clause in clauses:
        for index, pattern in enumerate(_SELF_CHECK_RES):
            if index == 0 and risky:
                continue
            match = pattern.search(clause)
            if match:
                return _who(match)
    return None


def _symptom_statement(prepared: str) -> bool:
    """Whether the user describes a symptom of their own, e.g. "I found a lump"."""

    return bool(re.search(_D, prepared)) and any(
        pattern.search(prepared) for pattern in _SYMPTOM_STATEMENT_RES
    )


def _who(match: "re.Match[str]") -> _Person:
    groups = match.groupdict()
    if groups.get("rel"):
        return _match_person(match)
    if groups.get("who") in {"he", "she", "they", "his", "her", "their"}:
        return _Person(name="", pronoun=_PRONOUN_SUBJECTS.get(groups["who"], "they"))
    return _YOU


# ---------------------------------------------------------------- disclosures

_SELF_VERBS = (
    "have been diagnosed with",
    "have just been diagnosed with",
    "was just diagnosed with",
    "was diagnosed with",
    "got diagnosed with",
    "just got diagnosed with",
    "just found out i have",
    "found out i have",
    "am being treated for",
    "am living with",
    "live with",
    "am fighting",
    "am battling",
    "am recovering from",
    "recovered from",
    "am in remission from",
    "am in remission",
    "am going through",
    "went through",
    "am undergoing",
    "underwent",
    "am about to start",
    "am starting",
    "am on",
    "am having",
    "have started",
    "started",
    "have finished",
    "finished",
    "completed",
    "have beaten",
    "have had",
    "have got",
    "have",
    "got",
    "had",
    "fought",
    "battled",
    "survived",
    "beat",
    "need",
    "am a",
    "am stage",
    "am terminal",
    "am dying of",
    "am dying from",
)
_OTHER_VERBS = (
    "has been diagnosed with",
    "has just been diagnosed with",
    "was just diagnosed with",
    "was diagnosed with",
    "got diagnosed with",
    "is being treated for",
    "is living with",
    "lives with",
    "lived with",
    "is fighting",
    "is battling",
    "is recovering from",
    "recovered from",
    "is in remission from",
    "is in remission",
    "is going through",
    "went through",
    "is undergoing",
    "underwent",
    "is about to start",
    "is starting",
    "is on",
    "was on",
    "is having",
    "has started",
    "started",
    "has finished",
    "finished",
    "has beaten",
    "has had",
    "has got",
    "has",
    "have",
    "had",
    "got",
    "fought",
    "battled",
    "survived",
    "beat",
    "needs",
    "is dying of",
    "is dying from",
    "died of",
    "died from",
    "died",
    "passed away from",
    "passed away",
    "lost her battle with",
    "lost his battle with",
    "lost their battle with",
    "lost her fight with",
    "lost his fight with",
    "are",
    "is",
    "was",
    "were",
)
_PAST_VERBS = frozenset(
    {
        "had",
        "have had",
        "has had",
        "survived",
        "beat",
        "have beaten",
        "has beaten",
        "fought",
        "battled",
        "recovered from",
        "went through",
        "finished",
        "have finished",
        "has finished",
        "completed",
        "underwent",
        "am in remission",
        "am in remission from",
        "is in remission",
        "is in remission from",
        "was",
        "were",
        "was on",
        "lived with",
    }
)
_BEREAVED_VERBS = frozenset(
    {
        "died of",
        "died from",
        "died",
        "passed away from",
        "passed away",
        "lost her battle with",
        "lost his battle with",
        "lost their battle with",
        "lost her fight with",
        "lost his fight with",
    }
)
_CLAUSE_BLOCK_RE = re.compile(
    r"\b(?:about|questions?|essays?|projects?|reports?|homework|assignments?|presentations?"
    r"|exams?|tests?|scans?|appointments?|fears?|worried|worry|worries|scared|afraid|scare"
    r"|concerns?|concerned|symptoms?|signs?|lumps?|risks?|history|family|genes?|mutations?"
    r"|screening|mammograms?|researchers?|research|doctors?|nurses?|oncologists?|specialists?"
    r"|surgeons?|scientists?|charit(?:y|ies)|fundrais\w*|volunteers?|no|never|not|heard|read"
    r"|reading|seen|learn\w*|idea|interest\w*|books?|articles?|videos?|films?|movies?"
    r"|podcasts?|dreams?|nightmares?|class|lectures?|course|degree|thesis|job|work\w*|stud\w*)\b"
)
_CLAUSE_END_RE = re.compile(
    r"\b(?:and|but|so|because|though|although|which|what|how|should|can|could|will|would"
    r"|is it|are there|do you|does it|i|she|he|they|we|you|it)\b"
)
_ADVERBS = r"(?:(?:just|recently|also|still|now|already|finally|both|all)\s+)?"


def _verb_alt(verbs: Sequence[str]) -> str:
    alts = (re.escape(verb).replace(r"\ ", r"\s+") for verb in sorted(verbs, key=len, reverse=True))
    # "diagnosed with" also covers "diagnosed as having".
    return "|".join(
        alt.replace(r"diagnosed\s+with", r"diagnosed\s+(?:with|as\s+having)") for alt in alts
    )


_SELF_DISCLOSURE_RE = re.compile(
    rf"\bi\s+{_ADVERBS}(?P<verb>{_verb_alt(_SELF_VERBS)})\b(?P<clause>(?:\s+[a-z0-9']+){{0,8}})"
)
_OTHER_DISCLOSURE_RE = re.compile(
    rf"{_MY_REL}\s+{_ADVERBS}(?P<verb>{_verb_alt(_OTHER_VERBS)})\b"
    r"(?P<clause>(?:\s+[a-z0-9']+){0,8})"
)
_PRONOUN_DISCLOSURE_RE = re.compile(
    rf"\b(?P<pronoun>he|she|they)\s+{_ADVERBS}(?P<verb>{_verb_alt(_OTHER_VERBS)})\b"
    r"(?P<clause>(?:\s+[a-z0-9']+){0,8})"
)
_HAVE_SOMEONE_RE = re.compile(
    rf"\bi (?:have|know) (?:a|an|two|three)\s+(?P<mods>{_MODS})(?P<rel>{_REL})\s+"
    rf"(?:with|who has|who is|who was|who is fighting|who is battling|battling|fighting"
    rf"|diagnosed with)\b{_FILLER}{{0,4}}?\s+{_D}"
)
_POSSESSIVE_DISCLOSURE_RE = re.compile(
    rf"{_MY_REL}'s\s+(?:(?!(?:has|have|had|is|was|were|are|got|gets)\b)[a-z0-9]+\s+){{0,3}}?"
    rf"(?:{_DISEASE}|{_TREATMENT})\b{_NOT_PERSONAL}"
)
_MY_DISEASE_RE = re.compile(
    rf"\bmy\s+(?:(?:{_KEY_WORD_ALT}|stage|\d+|metastatic|advanced|early|recurrent|secondary"
    rf"|terminal|aggressive|rare)\s+){{0,3}}(?:{_DISEASE}|{_TREATMENT})\b"
    r"(?!\s+(?:risks?|screening|tests?|scans?|scare|fears?|worr\w*|symptoms?|signs?|essays?"
    r"|projects?|research|class|charit\w*|insurance|polic\w*|awareness|knowledge|questions?"
    r"|homework|assignments?|reports?|presentations?)\b)"
)
_LOST_RE = re.compile(rf"\blost\s+(?:my|our)\s+(?P<mods>{_MODS})(?P<rel>{_REL})\s+to\b")
_TOOK_RE = re.compile(
    rf"{_D}\s+(?:took|killed|claimed|stole|took away)\s+(?:my|our)\s+(?P<mods>{_MODS})"
    rf"(?P<rel>{_REL})\b"
)
_BEREAVED_RE = re.compile(
    r"\b(?:died|dead|passed away|passed on|funeral|grieving|grief|lost (?:her|his|their)"
    r" (?:battle|fight))\b"
)
_PAST_CLAUSE_RE = re.compile(r"\b(?:survivors?|remission|free|gone|cured|all clear)\b")
_DISCLOSURE_TERM_RE = re.compile(rf"\b(?:{_DISEASE}|{_TREATMENT})\b{_NOT_PERSONAL}")
_SURVIVOR_RE = re.compile(
    rf"\b(?:{_DISEASE}\s+(?:patient|survivor|sufferer|warrior|fighter|thriver)s?|survivor of)\b"
)


@dataclass(frozen=True)
class _Disclosure:
    person: _Person
    tense: str  # "present", "past" or "bereaved"
    words: str = ""  # what was disclosed, e.g. "my mum has leukemia"


def _clause_ok(verb: str, clause: str) -> bool:
    clause = _CLAUSE_END_RE.split(clause)[0]
    if verb in {"am a"}:
        return bool(_SURVIVOR_RE.search(clause))
    if verb in {"is", "are", "was", "were"} and re.match(r"\s*an?\s", clause):
        if not _SURVIVOR_RE.search(clause):
            return False
    if re.match(r"\s*to\b", clause) or _CLAUSE_BLOCK_RE.search(clause):
        return False
    return bool(_DISCLOSURE_TERM_RE.search(clause))


def _tense(verb: str, clause: str) -> str:
    if verb in _BEREAVED_VERBS:
        return "bereaved"
    if verb in _PAST_VERBS or _PAST_CLAUSE_RE.search(clause):
        return "past"
    return "present"


def _disclosed(match: "re.Match[str]") -> str:
    """The words of a verb-and-clause disclosure match, up to the clause's end."""

    clause = _CLAUSE_END_RE.split(match.group("clause"))[0]
    return match.string[match.start() : match.start("clause")] + clause


def _disclosure(clauses: Sequence[str], prepared: str) -> Optional[_Disclosure]:
    """Recognise "I have breast cancer" or "my mum has leukemia"."""

    for pattern in (_LOST_RE, _TOOK_RE):
        match = pattern.search(prepared)
        if match:
            person = _match_person(match)
            return _Disclosure(person, "bereaved", match.group(0))
    bereaved = bool(_BEREAVED_RE.search(prepared))
    match = _POSSESSIVE_DISCLOSURE_RE.search(prepared)
    if match:
        person = _match_person(match)
        tense = "bereaved" if bereaved or person.late else "present"
        return _Disclosure(person, tense, match.group(0))
    for clause in clauses:
        match = _HAVE_SOMEONE_RE.search(clause)
        if match:
            person = _match_person(match)
            return _Disclosure(person, "present", match.group(0))
        match = _OTHER_DISCLOSURE_RE.search(clause)
        person = _match_person(match) if match else None
        if not (match and _clause_ok(match.group("verb"), match.group("clause"))):
            match = _PRONOUN_DISCLOSURE_RE.search(clause)
            person = _first_relation(prepared)
            if match and person is None:
                person = _Person(name="", pronoun=match.group("pronoun"))
        if match and person and _clause_ok(match.group("verb"), match.group("clause")):
            tense = _tense(re.sub(r"\s+", " ", match.group("verb")), match.group("clause"))
            if person.late or (bereaved and tense != "present"):
                tense = "bereaved"
            return _Disclosure(person, tense, _disclosed(match))
        match = _SELF_DISCLOSURE_RE.search(clause)
        if match and _clause_ok(match.group("verb"), match.group("clause")):
            verb = re.sub(r"\s+", " ", match.group("verb"))
            return _Disclosure(_YOU, _tense(verb, match.group("clause")), _disclosed(match))
    match = _MY_DISEASE_RE.search(prepared)
    if match:
        tense = "past" if _PAST_CLAUSE_RE.search(prepared) else "present"
        return _Disclosure(_YOU, tense, match.group(0))
    return None


_RECURRENCE_RE = re.compile(
    r"\b(?:is|has|have|did|could|might|will|would)\s+(?:(?:my|our|his|her|their|the)\s+"
    rf"(?:[a-z0-9']+\s+){{0,3}}?(?:{_DISEASE})|it)(?:\s+(?:have|has|be|been|already|now))*"
    r"\s+(?:back|come back|coming back|came back|returned|returning|spread|spreading|recurred"
    r"|recurring|metastasi[sz]ed)\b"
)


_GENERAL_WORRY_RE = re.compile(
    rf"\b{_WORRY}\b|\b{_DISEASE} scares?\b|\bwill i (?:get|develop)\b|\bam i going to"
    r" (?:get|develop)\b"
)


# ---------------------------------------------------------------- intents

_TOPICS_RE = re.compile(
    r"\bcancer topics\b|\b(?:types|kinds|sorts|forms|list) of cancers?\b(?!\s+(?:treat\w*"
    r"|therap\w*|drugs?|medicines?|medications?|screening|tests?))"
    r"|\blist (?:all |the )?(?:cancers|cancer types)\b|\bcancer types\b|\b(?:which|what)"
    r" cancers (?:do|does|can|are)\b|\bcancers (?:do )?you (?:know|cover)\b"
    r"|\bhow many (?:types|kinds) of cancer\b|\bbeat it topics\b"
)
_SURVIVAL_RE = re.compile(
    r"\bsurviv(?:al|e|ing)\b(?! of\b)|\bprognosis\b|\blife expectancy\b|\boutlook\b"
    r"|\bhow long (?:do|can|will|would|could|does) (?:i|you|people|he|she|they|someone"
    r"|my \w+) (?:have )?(?:live|survive|have left)\b|\b(?:fatal|deadly)\b|\bdeath rate\b"
    r"|\bmortality rate\b|\bcure rate\b|\b(?:5|five) year\b|\b(?:recurrence|relapse) rates?\b"
    r"|\b(?:chances?|odds|likel\w*|risk|common)\b.*\b(?:come|comes|coming) back\b"
)
_FACTS_RE = re.compile(
    r"\bstatistic\w*|\bstats\b|\bhow common\b|\bhow many (?:people|cases|deaths|new cases"
    r"|die)\b|\bprevalen\w*|\bincidence\b|\bworldwide\b|\bglobal(?:ly)?\b|\baround the world\b"
    r"|\bglobocan\b|\bnumber of (?:cases|deaths|people)\b|\bfacts\b|\bfigures\b"
    r"|\bmost common (?:cancers?|types?|kinds?|forms?)\b|\bleading cause\b|\bcancer deaths\b"
    r"|\bin 2050\b"
)
_CONTAGIOUS_RE = re.compile(
    r"\bcontagious\b|\binfectious\b|\btransmissible\b|\bcatch(?:ing|able)?\b(?!\s+(?:it\s+"
    r"|cancer\s+)?early\b)|\bspread (?:from |between )(?:person|people)\b"
)
# Common types beat-it has no entry for, so they aren't mistaken for one it has
# ("small bowel cancer" is not colorectal cancer).
_UNCOVERED_RE = re.compile(
    r"\b(?:mesotheliomas?|(?:testicular|testis|anal|vulvar|vulval|vaginal|penile|eye|ocular"
    r"|uveal|adrenal|appendix|appendiceal|gallbladder|gall bladder|thymus|thymic"
    r"|small intestine|small bowel|carcinoid|heart) (?:cancers?|tumors?|carcinomas?))\b"
)
# beat-it has no history of cancer research, so these get the honest fallback.
_HISTORY_RE = re.compile(
    r"\b(?:who|when)\s+(?:[a-z0-9']+\s+){0,4}?(?:discovered|invented|developed|founded)\b"
    r"|\bhistory\s+of\b|\b(?:discovery|invention)\s+of\b"
)
_FEEDS_RE = re.compile(
    r"\bnews\b|\bresearch\b|\bstudies\b|\bpapers?\b|\bbreakthroughs?\b(?! therap)"
    r"|\bheadlines?\b|\bupdates?\b"
)
_FILLER_WORDS = frozenset(
    "what is are tell me about more explain define describe info information on the a an"
    " please jarvis hey hi can you i want to know learn give some overview of basics in general"
    " simple terms briefly quick quickly so ok okay".split()
)

# (question, pattern, when) — "always" applies even when a cancer type is
# named, "define" only for "what is/does … mean" questions in that case, and
# "no_entry" only when no type is named.
_FAQ_RULES: Tuple[Tuple[str, str, str], ...] = (
    (
        "What is biomarker testing?",
        r"\bbiomarker\w*|\bgenomic (?:test\w*|profil\w*)|\bmolecular (?:test\w*|profil\w*)"
        r"|\btumor (?:genomic |genetic |molecular )?(?:test\w*|profil\w*)"
        r"|\bgenetic (?:test\w*|profil\w*) (?:of|on) (?:the |a |my )?tumor",
        "always",
    ),
    (
        "What is immunotherapy?",
        r"\bimmunotherap\w*|\bcheckpoint inhibitors?\b|\bcar t\b|\bbispecific\w*",
        "always",
    ),
    (
        "What is targeted therapy?",
        r"\btargeted (?:therap\w*|drugs?|treatments?|medicines?)\b",
        "always",
    ),
    (
        "What does accelerated approval mean?",
        r"\baccelerated approval\w*|\bfast track\w*|\bbreakthrough therap\w*|\bpriority review\b",
        "define",
    ),
    (
        "How can I find a clinical trial?",
        r"\bclinical (?:trials?|studies|study)\b|\btrials?\b|\bresearch stud(?:y|ies)\b",
        "always",
    ),
    (
        "What is cancer staging?",
        r"\bstaging\b|\btnm\b|\bstages\b|\bwhat (?:is|are|does) (?:a |the )?stages?\b"
        r"|\bstage (?:[a-z0-9]+ )?mean",
        "always",
    ),
    (
        "What are common side effects of treatment?",
        r"\bside effects?\b|\bhair loss\b|\blos(?:e|ing) (?:my |your |their |his |her )?hair\b"
        r"|\bnausea\b|\bneuropathy\b|\bafter effects?\b|\b(?:pain|tired\w*|fatigue|sick"
        r"|nause\w*|sore\w*|rash\w*|numb\w*|tingl\w*)\b.*\b(?:from|after|since|during"
        rf"|because of)\s+(?:my\s+|the\s+|his\s+|her\s+)?(?:{_CHEMO}|radiotherapy|radiation"
        r"|immunotherap\w*|treatment)",
        "always",
    ),
    (
        "What is palliative care?",
        r"\bpalliative\b|\bhospice\b|\bend of life\b|\bcomfort care\b|\bsupportive care\b",
        "always",
    ),
    (
        "Is cancer hereditary?",
        r"\bhereditar\w*|\binherit\w*|\bgenetic\w*|\bgenes?\b|\bruns? in (?:the |my |our |your "
        r"|his |her |their )?famil\w*|\bfamily history\b|\bbrca\w*|\blynch\b"
        r"|\bpass(?:ed)? (?:it )?(?:on|down)\b|\bin (?:my|our|the|his|her|their) family\b",
        "always",
    ),
    (
        "Where can I get support?",
        r"\bsupport\b|\bhelplines?\b|\bhotlines?\b|\bhelp line\b|\bcounsel+ing\b"
        r"|\bsomeone to talk to\b|\bcop(?:e|ing)\b|\bcaregivers?\b|\bcarers?\b|\bcaring for\b"
        r"|\bcharit(?:y|ies)\b|\bfinancial help\b",
        "always",
    ),
    (
        "Can cancer be prevented?",
        r"\bprevent\w*|\b(?:reduce|lower|cut) (?:my |your |the |our )?(?:risk|chances?)\b"
        r"|\bavoid (?:getting )?(?:cancer|it)\b",
        "no_entry",
    ),
    (
        "Are there new ways to get screened for cancer?",
        r"\bnew (?:ways?|tests?|methods?|options?)\b.*\bscreen\w*|\bscreen\w*.*\bnew\b"
        r"|\bself (?:collect\w*|sampl\w*|test\w*)|\bhome (?:test\w*|kits?|screening)\b"
        r"|\bblood tests?\b",
        "no_entry",
    ),
)
_FAQ_RES = tuple((question, re.compile(pattern), when) for question, pattern, when in _FAQ_RULES)
_DEFINE_RE = re.compile(r"\bwhat (?:is|are|does)\b|\bmean(?:s|ing)?\b|\bexplain\b|\bdefin\w*")
# A follow-up to suggest when an FAQ answers a question about one type.
_FAQ_POINTERS: Dict[str, str] = {
    "What is biomarker testing?": "treatments",
    "What is immunotherapy?": "medicines",
    "What is targeted therapy?": "medicines",
    "What does accelerated approval mean?": "approvals",
    "How can I find a clinical trial?": "approvals",
    "What are common side effects of treatment?": "treatments",
    "Is cancer hereditary?": "risk factors",
}

_SECTION_ORDER = ("symptoms", "risk factors", "screening", "treatments", "medicines", "approvals")
_APPROVALS_RE = re.compile(
    r"\b(?:fda\s+)?approv\w*(?:\s+(?:drugs?|medicines?|medications?|treatments?|therap\w*))?"
    r"|\bfda\b|\bwhat is new\b|\b(?:latest|newest|recent|new)\s+(?:[a-z]+\s+)?(?:drugs?"
    r"|medicines?|medications?|treatments?|therap(?:y|ies)|approvals?|options?)\b"
    r"|\brecently approved\b"
)
_SECTION_RES: Tuple[Tuple[str, "re.Pattern[str]"], ...] = tuple(
    (name, re.compile(pattern))
    for name, pattern in (
        (
            "medicines",
            r"\bmedicines?\b|\bmedications?\b|\bdrugs?\b|\bmeds\b|\bpills?\b|\btablets?\b"
            r"|\bprescri\w*",
        ),
        (
            "treatments",
            r"\btreat(?:s|ed|ing|ment|ments|able)?\b|\btherap(?:y|ies)\b|\bcur(?:e|es|ed|able"
            r"|ing)\b|\bsurgery\b|\bsurgical\b|\boperations?\b|\bmanage(?:d|ment)?\b"
            rf"|\b{_CHEMO}\b|\bradiotherapy\b|\bradiation\b|\bget rid of\b",
        ),
        (
            "screening",
            r"\bscreen\w*|\bearly detection\b|\bdetect\w*|\bmammogra\w*|\bpap (?:tests?|smears?)\b"
            r"|\bsmear tests?\b|\bcolonoscop\w*|\bpsa tests?\b|\bcheck ?ups?\b"
            r"|\bget(?:ting)? checked\b|\bcheck(?:ed)? for\b"
            r"|\b(?:find|catch) (?:it |cancer )?early\b"
            r"|\btest(?:s|ed|ing)? for\b",
        ),
        (
            "symptoms",
            r"\bsymptoms?\b|\bsigns?\b|\bhow (?:do|would|can|could) (?:i|you|we|they|someone"
            r"|people) (?:know|tell)\b|\bfeel like\b|\blook like\b|\bindications?\b",
        ),
        (
            "risk factors",
            r"\brisks?\b|\bcaus(?:e|es|ed|ing)\b|\bwhy (?:do|does|did) (?:people|someone|some"
            r" people|you|we|i|he|she|they) (?:get|develop)\b|\bwho gets\b|\bchances? of\b"
            r"|\bmore likely\b|\blikely to (?:get|develop)\b|\bprevent\w*|\bavoid\w*"
            r"|\breduce\b|\bcontribut\w*",
        ),
    )
)
_WEAK_TREATMENT_RE = re.compile(r"\boptions?\b")


def _sections(prepared: str) -> List[str]:
    """Return the entry sections asked about, in beat-it's page order."""

    found = set()
    remaining = prepared
    if _APPROVALS_RE.search(prepared):
        found.add("approvals")
        remaining = _APPROVALS_RE.sub(" ", prepared)
    for name, pattern in _SECTION_RES:
        if pattern.search(remaining):
            found.add(name)
    if not found and _WEAK_TREATMENT_RE.search(remaining):
        found.add("treatments")
    return [name for name in _SECTION_ORDER if name in found]


def _faq(prepared: str, entry: Optional[Cancer]) -> Optional[Faq]:
    for question, pattern, when in _FAQ_RES:
        if not pattern.search(prepared):
            continue
        if entry is None or when == "always":
            return _FAQ_BY_QUESTION[question]
        if when == "define" and _DEFINE_RE.search(prepared):
            return _FAQ_BY_QUESTION[question]
    if entry is None:
        questions = {_prepare(faq.question): faq for faq in FAQS}
        close = get_close_matches(prepared, list(questions), n=1, cutoff=0.88)
        if close:
            return questions[close[0]]
    return None


def _is_bare(prepared: str) -> bool:
    words = [word for word in prepared.split() if word not in _FILLER_WORDS]
    return words in (["cancer"], ["cancers"])


# ---------------------------------------------------------------- formatting


def _preview(items: Sequence[str], count: int = 3) -> str:
    shown = "; ".join(items[:count])
    extra = len(items) - count
    return f"{shown}; and {extra} more" if extra > 0 else shown


def _finish(lines: List[str], disclaimer: bool = True) -> str:
    if disclaimer:
        lines.append(DISCLAIMER)
    lines.append(CREDIT)
    return "\n".join(lines)


def _reviewed(entry: Cancer) -> str:
    return f"Reviewed by beat-it on {_date(entry.reviewed)}."


def _overview(entry: Cancer) -> List[str]:
    also = ["risk factors", "screening", f"{len(entry.medicines)} example medicines"]
    if entry.approvals:
        since = min(approval.date for approval in entry.approvals)[:4]
        also.append(f"{len(entry.approvals)} FDA approvals since {since}")
    listed = ", ".join(also[:-1]) + " and " + also[-1]
    return [
        f"{entry.name} ({entry.group})",
        entry.summary,
        f"- Common symptoms: {_preview(entry.symptoms)}",
        f"- Treatments: {_preview(entry.treatments)}",
        f"- Also listed: {listed}",
        f"Say '{entry.short} treatments' for more, or ask about its symptoms, risk factors, "
        "screening, medicines or approvals.",
        f"NCI: {entry.nci}",
        _reviewed(entry),
    ]


def _bullets(items: Sequence[str], limit: int) -> List[str]:
    lines = [f"- {item}" for item in items[:limit]]
    if len(items) > limit:
        lines.append(f"- and {len(items) - limit} more on the beat-it site")
    return lines


def _medicine(entry: Cancer, medicine: Medicine) -> str:
    label = medicine.name
    if medicine.since and _months_between(medicine.since, entry.reviewed) < 24:
        label += f" (new FDA approval: {_date(medicine.since)})"
    return f"{label} — {medicine.use}"


def _approval(approval: Approval) -> str:
    return f"{_date(approval.date)} — {approval.drug}: {approval.text}"


def _section(entry: Cancer, name: str) -> List[str]:
    if name == "symptoms":
        return [
            f"Common symptoms of {entry.label}, as listed by beat-it:",
            *_bullets(entry.symptoms, 8),
            "These can have other causes too; see a doctor about any that last or worry you.",
            _reviewed(entry),
        ]
    if name == "risk factors":
        return [
            f"Risk factors for {entry.label}, as listed by beat-it:",
            *_bullets(entry.risk_factors, 8),
            "Having a risk factor doesn't mean you'll get cancer.",
            _reviewed(entry),
        ]
    if name == "screening":
        lines = [f"Screening for {entry.label}:", entry.screening]
        if entry.screening_source:
            source = entry.screening_source
            lines.append(f"Source: {source.name} ({source.url})")
        return lines + [_reviewed(entry)]
    if name == "treatments":
        return [
            f"Treatment options for {entry.label}, as listed by beat-it:",
            *_bullets(entry.treatments, 8),
            TREATMENT_NOTE,
            _reviewed(entry),
        ]
    if name == "medicines":
        total = len(entry.medicines)
        shown = min(total, 6)
        count = f"{shown} of {total}" if shown < total else str(total)
        return [
            f"Example medicines for {entry.label} ({count}):",
            *_bullets([_medicine(entry, medicine) for medicine in entry.medicines], 6),
            MEDICINES_NOTE,
            "Medicines and approvals last updated from official sources (FDA, NCI) on "
            f"{_date(entry.reviewed)}.",
        ]
    if not entry.approvals:
        return [
            f"beat-it lists no recent FDA approvals for {entry.label}.",
            _reviewed(entry),
        ]
    total = len(entry.approvals)
    header = (
        f"Recent FDA approvals for {entry.label} (newest {min(total, 5)} of {total}):"
        if total > 5
        else f"Recent FDA approvals for {entry.label}:"
    )
    return [
        header,
        *_bullets([_approval(approval) for approval in entry.approvals], 5),
        f"As listed by beat-it on {_date(entry.reviewed)}; newer approvals may be missing.",
    ]


_COMPACT_LABELS = {
    "symptoms": "Symptoms",
    "risk factors": "Risk factors",
    "treatments": "Treatments",
}


def _compact(entry: Cancer, names: Sequence[str]) -> List[str]:
    lines = [entry.name]
    for name in names:
        if name in _COMPACT_LABELS:
            items = getattr(entry, name.replace(" ", "_"))
            lines.append(f"- {_COMPACT_LABELS[name]}: {_preview(items)}")
        elif name == "screening":
            lines.append(f"- Screening: {entry.screening}")
        elif name == "medicines":
            lines.append(f"- Medicines: {_preview([m.name for m in entry.medicines])}")
        elif entry.approvals:
            newest = entry.approvals[0]
            lines.append(
                f"- Recent FDA approvals: {len(entry.approvals)}, newest "
                f"{_date(newest.date)} ({newest.drug})"
            )
    asks = " or ".join(f"'{entry.short} {name}'" for name in names[:2])
    lines.append(f"Say {asks} for the full list.")
    lines.append(_reviewed(entry))
    return lines


def _faq_lines(faq: Faq, entry: Optional[Cancer]) -> List[str]:
    lines = [faq.question, faq.answer, f"More: {faq.link}"]
    if entry is not None:
        follow = _FAQ_POINTERS.get(faq.question)
        ask = f"{entry.short} {follow}" if follow else entry.short
        lines.append(f"For {entry.label} specifically, say '{ask}'.")
    return lines


def _fact_line(fact: Fact) -> str:
    return f"- {fact.value} {fact.label.rstrip('.')} ({fact.source})"


_GENERIC_FACT_WORDS = frozenset({"cancer", "cancers", "tumor", "tumors"})


def _facts(entry: Optional[Cancer]) -> List[str]:
    lines = [f"{FACTS_TITLE}: {FACTS_INTRO}"]
    if entry is not None:
        names = {entry.id, *re.findall(r"[a-z]+", _strip_parenthetical(entry.name).lower())}
        words = {word for word in names if len(word) > 3} - _GENERIC_FACT_WORDS
        matching = [
            fact for fact in FACTS if words & set(re.findall(r"[a-z]+", fact.label.lower()))
        ]
        if matching:
            return lines + [_fact_line(fact) for fact in matching]
        lines.append(f"beat-it's worldwide figures don't break out {entry.label}. Overall:")
    return lines + [_fact_line(fact) for fact in FACTS]


def _survival(entry: Optional[Cancer]) -> List[str]:
    lines = [
        "beat-it doesn't list survival rates or outlook. They depend on the type, the stage "
        "and the person, so a care team is the best source.",
    ]
    if entry is not None:
        lines.append(f"NCI's page on {entry.label}: {entry.nci}")
    return lines


def _contagious() -> List[str]:
    lines = [
        "beat-it's notes don't say whether cancer itself can pass from person to person — a "
        "doctor or NCI (https://www.cancer.gov) can answer that.",
        "It does list some infections as risk factors:",
    ]
    for cancer in CANCERS:
        found = [risk for risk in cancer.risk_factors if _INFECTION_RE.search(risk)]
        if found:
            lines.append(f"- {cancer.name}: {'; '.join(found)}")
    lines.append("Say 'can cancer be prevented?' for ways to lower risk.")
    return lines


_INFECTION_RE = re.compile(r"infection|hepatitis|virus|\bhpv\b|pylori", re.IGNORECASE)


def _uncovered(name: str) -> List[str]:
    return [
        f"beat-it doesn't have an entry for {name}. It covers {len(CANCERS)} types — say "
        "'cancer topics' for the list.",
        "NCI covers many more types: https://www.cancer.gov/types",
    ]


def _feeds(entry: Optional[Cancer]) -> List[str]:
    lines = [
        "beat-it's research, trial and news feeds are refreshed daily on its site, so they "
        "aren't available offline here.",
    ]
    if entry is None:
        lines.append(
            "I can share the FDA approvals beat-it lists — say e.g. 'lung cancer approvals'."
        )
        return lines
    return lines + _section(entry, "approvals")


def _general_section(name: str) -> List[str]:
    """Answer a section question when no cancer type is named."""

    if name == "approvals":
        newest: Dict[Tuple[str, str], Tuple[Approval, Cancer]] = {}
        for cancer in CANCERS:
            for approval in cancer.approvals:
                newest.setdefault((approval.date, approval.drug), (approval, cancer))
        latest = sorted(newest.values(), key=lambda pair: pair[0].date, reverse=True)[:5]
        return [
            "The newest FDA cancer approvals beat-it lists:",
            *(f"- {_approval(approval)} ({cancer.name})" for approval, cancer in latest),
            f"As listed by beat-it on {_date(REVIEWED)}; newer approvals may be missing.",
            "Say e.g. 'lung cancer approvals' for one type.",
        ]
    if name == "screening":
        sourced = [cancer.name for cancer in CANCERS if cancer.screening_source]
        return [
            "Screening advice depends on the cancer type. beat-it cites a guideline source "
            f"for: {', '.join(sourced)}.",
            "Say e.g. 'breast cancer screening' for details, or ask 'are there new ways to get "
            "screened for cancer?'.",
        ]
    if name == "symptoms":
        return [
            f"Symptoms depend on the type of cancer. beat-it lists them for each of its "
            f"{len(CANCERS)} types — say e.g. 'lung cancer symptoms'.",
            "If you've noticed a change that worries you, please see a doctor.",
        ]
    if name == "medicines":
        return [
            f"beat-it lists example medicines for each of its {len(CANCERS)} cancer types — say "
            "e.g. 'breast cancer medicines'.",
        ]
    if name == "risk factors":
        return [
            f"Risk factors depend on the type of cancer. beat-it lists them for each of its "
            f"{len(CANCERS)} types — say e.g. 'lung cancer risk factors'.",
            *_faq_lines(_FAQ_BY_QUESTION["Can cancer be prevented?"], None),
        ]
    return _faq_lines(_FAQ_BY_QUESTION["What are the main types of cancer treatment?"], None)


def _body(prepared: str, entry: Optional[Cancer]) -> Optional[List[str]]:
    """Return the lines answering ``prepared``, without the closing lines."""

    if _TOPICS_RE.search(prepared):
        return _topic_lines()
    if _SURVIVAL_RE.search(prepared):
        return _survival(entry)
    if _FACTS_RE.search(prepared):
        return _facts(entry)
    if _CONTAGIOUS_RE.search(prepared):
        return _contagious()
    faq = _faq(prepared, entry)
    if faq is not None:
        return _faq_lines(faq, entry)
    if _FEEDS_RE.search(prepared):
        return _feeds(entry)
    sections = _sections(prepared)
    if entry is None:
        if sections:
            return _general_section(sections[0])
        if _is_bare(prepared):
            return _faq_lines(_FAQ_BY_QUESTION["What is cancer?"], None)
        return None
    if len(sections) == 1:
        return _section(entry, sections[0])
    if sections:
        return _compact(entry, sections)
    return None


def _topic_lines() -> List[str]:
    lines = [f"beat-it covers {len(CANCERS)} cancer types (reviewed {_date(REVIEWED)}):"]
    groups: List[str] = []
    for cancer in CANCERS:
        if cancer.group not in groups:
            groups.append(cancer.group)
    for group in groups:
        names = ", ".join(cancer.name for cancer in CANCERS if cancer.group == group)
        lines.append(f"- {group}: {names}")
    lines.append(
        "Ask e.g. 'lung cancer', 'leukemia symptoms', 'breast cancer medicines' or "
        "'is cancer hereditary?'."
    )
    return lines


# ---------------------------------------------------------------- replies


_WORRY_RE = re.compile(rf"\b{_WORRY}\b")
_SCARED_RE = re.compile(r"scared|afraid|frightened|terrified|petrified|fear|panick|freaking")
_NEGATED_RE = re.compile(
    r"\b(?:not|no|nothing)(?:\s+(?:to|too|that|so|very|really|at all|need to))?\s+$"
)


def _worry_opening(person: _Person, prepared: str) -> List[str]:
    """A kind first line when the user says they are worried or scared ("not worried" isn't)."""

    for match in _WORRY_RE.finditer(prepared):
        if _NEGATED_RE.search(prepared[: match.start()]):
            continue
        if not person.is_user:
            return [f"It's understandable to be worried about {person.your()}."]
        feeling = "feel scared" if _SCARED_RE.match(match.group(0)) else "be worried"
        return [f"It's understandable to {feeling}."]
    return []


def _self_check_reply(entry: Optional[Cancer], person: _Person, prepared: str) -> str:
    lines = _worry_opening(person, prepared)
    if person.is_user:
        lines += [
            "I can't diagnose cancer or tell what a symptom means — a doctor who can examine "
            "you can.",
            "Please see a doctor soon to get it checked, and get urgent care if a symptom is "
            "severe or came on suddenly.",
        ]
    else:
        them = person.your()
        lines += [
            "I can't diagnose cancer or tell what a symptom means — a doctor who can examine "
            f"{them} can.",
            f"Please encourage {them} to see a doctor soon, and to get urgent care if a symptom "
            "is severe or came on suddenly.",
        ]
    lines.append(
        "Having a symptom doesn't mean it's cancer — many conditions cause the same signs — "
        "but it's worth getting checked."
    )
    if entry is not None and entry.symptoms:
        lines.append(f"General warning signs beat-it lists for {entry.label}:")
        lines += [f"- {symptom}" for symptom in entry.symptoms]
        lines.append(_reviewed(entry))
    return _finish(lines)


def _acknowledge(disclosure: _Disclosure) -> str:
    person = disclosure.person
    if disclosure.tense == "bereaved":
        if not person.name:
            return "I'm so sorry for your loss."
        return f"I'm so sorry about {person.your()}."
    if person.is_user:
        if disclosure.tense == "past":
            return "That's a lot to have been through."
        return "I'm sorry you're dealing with this."
    if disclosure.tense == "past":
        return f"That must have been a lot for {person.your()} and for you."
    return f"I'm sorry {person.subject()} {person.verb} going through this."


def _disclosure_reply(
    disclosure: _Disclosure, entry: Optional[Cancer], prepared: str, uncovered: str = ""
) -> str:
    person = disclosure.person
    if entry is None and person.child:
        entry = next(cancer for cancer in CANCERS if cancer.id == "childhood")
    lines = [_acknowledge(disclosure)]
    # Answer what else was asked: "my wife has breast cancer, what are the
    # treatments?" wants treatments, but "I'm on chemo" alone doesn't.
    rest = prepared.replace(disclosure.words.strip(), " ", 1) if disclosure.words else prepared
    body = _body(rest, entry)
    if disclosure.tense == "bereaved":
        if body is None:
            lines.append(
                "If it would help, say 'cancer support' for helplines and support groups."
            )
            return _finish(lines, disclaimer=False)
        return _finish(lines + body)
    if body is not None:
        lines += body
    elif entry is not None:
        lines += [
            f"{entry.name}: {entry.summary}",
            "I can show its treatments, medicines or recent FDA approvals — say "
            f"'{entry.short} treatments', '{entry.short} medicines' or "
            f"'{entry.short} approvals'.",
        ]
    elif uncovered:
        lines += _uncovered(uncovered)
    else:
        lines += [
            "If you tell me the type — for example 'lung cancer' — I can share an overview, "
            "treatments, medicines or recent FDA approvals.",
            "For helplines and support groups, say 'cancer support'.",
        ]
    if _symptom_statement(prepared):
        lines.append(
            "Bring any new or worsening symptoms, and your questions, to "
            f"{person.possessive()} care team soon — get urgent care if a symptom is severe or "
            "came on suddenly."
        )
    else:
        lines.append(
            "It can help to write your questions down and bring them to "
            f"{person.possessive()} care team."
        )
    if body is None and entry is not None:
        lines.append(f"{_reviewed(entry)} NCI: {entry.nci}")
    return _finish(lines)


def _recurrence_reply(person: _Person) -> str:
    lines = [
        "That's an understandable worry.",
        "I can't tell whether cancer has come back or spread, or predict whether it will — "
        f"{person.possessive()} care team can, with an examination and tests if needed.",
        "Please contact them soon, and get urgent care if a symptom is severe or came on "
        "suddenly.",
    ]
    return _finish(lines)


def _worry_reply(entry: Optional[Cancer], prepared: str) -> str:
    lines = [
        "It's understandable to worry about cancer. I can't assess your own risk, but a doctor "
        "can talk it through with you, including which screening suits you.",
    ]
    body = _body(prepared, entry)
    if body is None and entry is not None:
        body = _section(entry, "risk factors")
    if body is not None:
        lines += body
    else:
        lines.append(
            "For general guidance, ask 'can cancer be prevented?' or 'is cancer hereditary?'."
        )
    lines.append(
        "If you've noticed a symptom that worries you, please get it checked soon — urgently "
        "if it's severe or came on suddenly."
    )
    return _finish(lines)


def _pet_reply(prepared: str) -> str:
    match = _OWN_PET_RE.search(prepared)
    lines = []
    if match:
        lines.append(f"I'm sorry about your {match.group('pet')}.")
    lines.append(
        "beat-it covers cancer in people, so a vet is the best person to ask about cancer in "
        "animals."
    )
    return _finish(lines, disclaimer=False)


def topics() -> str:
    """List the cancer types beat-it covers, grouped as on its site."""

    return _finish(_topic_lines())


def answer(text: str) -> Optional[str]:
    """Answer a question about cancer from beat-it's notes.

    Returns ``None`` when ``text`` is not about cancer in people (no cancer
    word, the star sign, the Tropic of Cancer, "a cancer on society"), so the
    caller can try something else. Every other reply is plain text that ends
    with :data:`DISCLAIMER` (for medical content) and :data:`CREDIT`.
    """

    prepared = _prepare(text or "")
    if not prepared or _NOT_MEDICAL_RE.search(prepared):
        return None
    gist = bool(_GIST_RE.search(text or "")) and not _GIST_OF_RE.search(prepared)
    if not _has_context(prepared, gist):
        return None
    if _PET_RE.search(prepared):
        return _pet_reply(prepared)
    clauses = _clauses(text) or [prepared]
    found = _UNCOVERED_RE.search(prepared)
    uncovered = found.group(0) if found else ""
    lookup = prepared.replace(uncovered, " ") if uncovered else prepared
    lookup = _ACRONYM_ELSEWHERE_RE.sub(" ", lookup)
    entry = _find_entry(lookup, context=True, gist=gist)

    possessive = _POSSESSIVE_DISCLOSURE_RE.search(prepared)
    mine = _MY_DISEASE_RE.search(prepared)
    if not (possessive or mine):
        person = _self_check(clauses, prepared)
        if person is not None:
            return _self_check_reply(entry, person, prepared)
    disclosure = _disclosure(clauses, prepared)
    if _RECURRENCE_RE.search(prepared) and (disclosure is None or disclosure.tense != "bereaved"):
        person = disclosure.person if disclosure else (_first_relation(prepared) or _YOU)
        return _recurrence_reply(person)
    if disclosure is not None:
        return _disclosure_reply(disclosure, entry, prepared, uncovered)
    if _symptom_statement(prepared):
        return _self_check_reply(entry, _YOU, prepared)
    if _GENERAL_WORRY_RE.search(prepared):
        return _worry_reply(entry, prepared)

    history = _HISTORY_RE.search(prepared)
    body = None if history else _body(prepared, entry)
    if body is None and entry is not None and not history:
        body = _overview(entry)
    if entry is None and uncovered:
        faq = _faq(prepared, None)
        body = _uncovered(uncovered) + (_faq_lines(faq, None) if faq else [])
    if body is None:
        body = [
            "beat-it's notes don't cover that question. It answers questions like 'what is "
            "cancer?', 'can cancer be prevented?' and 'is cancer hereditary?', and covers "
            f"{len(CANCERS)} cancer types — say 'cancer topics' for the list.",
        ]
    return _finish(body)
