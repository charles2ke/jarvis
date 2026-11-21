"""Investment maths on numbers you type: DCF, CAPM, technicals, risk and DRIP.

Portfolio-Watcher (https://charles2ke.github.io/Portfolio-Watcher/, source at
https://github.com/charles2ke/Portfolio-Watcher) is the user's own research
app. Jarvis keeps no copy of its maths: the figures in every reply, default
rates and settings included, come from the project's TypeScript in
``src/research/``, run from the ``projects/Portfolio-Watcher`` submodule by
``bridges/portfolio-watcher.mjs`` with Node.js, once per reply. This module
reads the request and words the answer.

:func:`solve` answers discounted cash flow (DCF) valuations, CAPM cost of
equity, Fibonacci retracements, moving averages, RSI, MACD, Bollinger bands,
risk and return statistics, and dividend reinvestment (DRIP) projections.
Where a request doesn't map one to one onto the project's functions:

* A DCF runs through the project's revenue-based model with the typed free
  cash flow standing in for revenue at a 100% margin with nothing taken off,
  so the forecast is that cash flow growing at the typed rate. An exit
  multiple applies to EBITDA, which is the same cash flow here.
* A beta becomes a cost of equity the way the project estimates a company's
  discount rate, with the project's own risk-free rate and equity risk
  premium; typed rates or a market return can't be used, and the reply says
  so.
* Settings left out take the project's defaults: DCF horizon and terminal
  growth, RSI, MACD and Bollinger settings, VaR confidence and DRIP horizons.
  A moving average with no period uses every value typed. Volatility is
  annualised the project's way, which treats the numbers as daily.
* There is no Sharpe ratio: the project has none for typed numbers. An
  annualised return comes only from typed prices, through the project's
  return profile, which treats them as daily.

Nothing here fetches market data: only the numbers in the request are used,
and every reply says it is general education, not advice. :func:`solve`
returns ``None`` for other text without needing the project. When the
project or Node.js is missing it raises
:class:`jarvis.projects.ProjectUnavailable` with setup steps.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from jarvis import projects

__all__ = [
    "CREDIT",
    "DISCLAIMER",
    "PROJECT",
    "REPO_URL",
    "SITE_URL",
    "TOPICS",
    "solve",
    "usage",
]

PROJECT = "Portfolio-Watcher"
SITE_URL = projects.PROJECTS[PROJECT].site
REPO_URL = projects.PROJECTS[PROJECT].repo
CREDIT = f"From {PROJECT}: {SITE_URL}"
DISCLAIMER = (
    "General education only, not investment advice — past performance and "
    "model outputs do not predict future returns."
)

TOPICS: Tuple[str, ...] = (
    "Discounted cash flow (DCF)",
    "CAPM cost of equity",
    "Simple moving average (SMA)",
    "Exponential moving average (EMA)",
    "RSI",
    "MACD",
    "Bollinger bands",
    "Fibonacci retracement",
    "Volatility",
    "Value at risk (VaR)",
    "Expected shortfall",
    "Max drawdown",
    "Return statistics",
    "Dividend reinvestment (DRIP)",
)

# Jarvis's own limits on a typed horizon.
_MAX_DCF_YEARS = 50
_MAX_DRIP_YEARS = 100

Series = List[Optional[float]]


# ---------------------------------------------------- asking the project


def _finite(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_finite(item) for item in value.values())
    if isinstance(value, list):
        return all(_finite(item) for item in value)
    return True


def _ask(action: str, payload: Dict[str, Any]) -> Any:
    """Run one of the adapter's actions on the numbers read from the request."""
    if not _finite(payload):
        raise ValueError("one of those numbers is too large to work with")
    return projects.call(PROJECT, action, payload)


def _unusable(key: str) -> projects.ProjectError:
    return projects.ProjectError(f"{PROJECT} gave no usable {key!r}")


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _number(data: Any, key: str) -> float:
    value = data.get(key) if isinstance(data, dict) else None
    if not _is_number(value):
        raise _unusable(key)
    return float(value)


def _optional(data: Any, key: str) -> Optional[float]:
    """A number the project may leave out (``null``)."""
    if not isinstance(data, dict):
        raise _unusable(key)
    if data.get(key) is None:
        return None
    return _number(data, key)


def _whole(data: Any, key: str) -> int:
    value = _number(data, key)
    if not value.is_integer():
        raise _unusable(key)
    return int(value)


def _series(data: Any, key: str, length: int) -> Series:
    """One value, or ``None`` where there is none yet, for each value typed."""
    value = data.get(key) if isinstance(data, dict) else None
    if (
        not isinstance(value, list)
        or len(value) != length
        or not all(item is None or _is_number(item) for item in value)
    ):
        raise _unusable(key)
    return [None if item is None else float(item) for item in value]


def _rows(data: Any, key: str) -> List[Dict[str, Any]]:
    value = data.get(key) if isinstance(data, dict) else None
    if not isinstance(value, list) or not value or not all(isinstance(row, dict) for row in value):
        raise _unusable(key)
    return value


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


# ---------------------------------------------------------------- parsing

_SCALES: Dict[str, float] = {
    "k": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "mn": 1e6,
    "mm": 1e6,
    "million": 1e6,
    "b": 1e9,
    "bn": 1e9,
    "billion": 1e9,
    "tn": 1e12,
    "trillion": 1e12,
}

# A whole number such as "1,250.5", "8", ".5" or "-2", never part of a longer
# number or word (so "100-150" reads as 100 and 150).
_NUM = (
    r"(?<![\w.])-?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
    r"(?!\d)(?!\.\d)(?!,\d{3}(?!\d))"
)
_PCT = r"\s*(?:%|percent\b|per\s*cent\b|pct\b)"
# Every value pattern names its number "value" so overlapping readings of
# the same typed number can be detected.
_AMOUNT = (
    r"(?:(?<![\w.])(?P<neg>-)\s?)?(?P<cur>[$£€¥₹])?\s?(?P<value>" + _NUM + r")"
    r"(?:\s?(?P<word>thousand|million|billion|trillion|mn|mm|bn|tn)\b"
    r"|(?P<letter>[kmb])\b)?"
    r"(?!" + _PCT + r"|[\s-]*(?:x|times|years?|yrs?)\b|\s*\*)"
)
_RATE = (
    r"(?P<value>" + _NUM + r")(?P<pct>" + _PCT + r")?"
    r"(?![kmb]\b)(?!\s*(?:x|times|years?|yrs?|thousand|million|billion|"
    r"trillion|mn|mm|bn|tn|shares?)\b|\s*\*)"
)
_PCT_VALUE = r"(?P<value>" + _NUM + r")" + _PCT
_NUMBER_VALUE = r"(?P<value>" + _NUM + r")"
# Words allowed between a keyword and its value: "growth of 8%", "wacc = 9".
_FILL = (
    r"\s*(?:(?:[=:~≈]|(?:of|is|was|at|about|around|roughly|approximately|"
    r"currently|equal\s+to|equals|base|by)\b)\s*)*"
)

_NUMBER_WORDS: Dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
    "twenty-five": 25,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
}
_COUNT = (
    r"(?P<count>(?<![\d.])\d+|"
    + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
    + r")"
)
_YEARS_PATTERNS = (
    r"\b" + _COUNT + r"[- ]?(?:years?|yrs?)\b",
    r"\b(?:years?|horizon)\s*(?:of|=|:)?\s*" + _COUNT + r"\b",
)


def _clean(text: str) -> str:
    """Lower-case text with Unicode minus signs and ellipses normalised."""
    text = text.replace("\u2212", "-").replace("\u2026", " ").replace("...", " ")
    return text.replace("\u00a0", " ").lower()


def _amount(match: "re.Match[str]") -> float:
    value = float(match.group("value").replace(",", ""))
    scale = match.group("word") or match.group("letter")
    if scale:
        value *= _SCALES[scale]
    return -value if match.group("neg") else value


def _number_after(text: str, keyword: str) -> Optional[float]:
    match = re.search(keyword + _FILL + _NUMBER_VALUE + r"(?!" + _PCT + r")", text)
    return float(match.group("value").replace(",", "")) if match else None


@dataclass(frozen=True)
class _Field:
    """A value to read: ``after`` patterns put the keyword before the number
    ("growth 8%"), ``before`` patterns put it after ("8% growth")."""

    name: str
    after: Tuple[str, ...] = ()
    before: Tuple[str, ...] = ()
    # "rate" (percent -> fraction), "percent" (kept as typed), "amount" or "number"
    kind: str = "rate"


@dataclass(frozen=True)
class _Candidate:
    field: str
    keyword_first: bool
    span: Tuple[int, int]
    value: float


def _convert(kind: str, match: "re.Match[str]") -> float:
    if kind == "amount":
        return _amount(match)
    value = float(match.group("value").replace(",", ""))
    return value / 100 if kind == "rate" else value


def _overlaps(span: Tuple[int, int], spans: Sequence[Tuple[int, int]]) -> bool:
    return any(span[0] < end and start < span[1] for start, end in spans)


def _read_fields(
    text: str,
    fields: Sequence[_Field],
    taken: Sequence[Tuple[int, int]] = (),
    spans: Optional[Dict[str, Tuple[int, int]]] = None,
) -> Dict[str, float]:
    """Read ``fields`` from ``text`` without giving one number to two fields.

    In "growth 8% discount 9%" the 8% sits between two keywords. A number
    goes to the only field that can claim it; when two fields still compete,
    the request's own style decides: keyword first ("growth 8%") or value
    first ("8% growth"), judged by its first recognised number. Numbers in
    ``taken`` are skipped; ``spans``, if given, receives each chosen number's
    position.
    """
    candidates: Dict[str, List[_Candidate]] = {}
    for field in fields:
        found: List[_Candidate] = []
        for keyword_first, patterns in ((True, field.after), (False, field.before)):
            for pattern in patterns:
                for match in re.finditer(pattern, text):
                    found.append(
                        _Candidate(
                            field.name,
                            keyword_first,
                            match.span("value"),
                            _convert(field.kind, match),
                        )
                    )
        candidates[field.name] = found
    every = [c for found in candidates.values() for c in found]
    first_start = min((c.span[0] for c in every), default=0)
    keyword_style = any(c.keyword_first for c in every if c.span[0] == first_start)
    claimed: List[Tuple[int, int]] = list(taken)
    values: Dict[str, float] = {}

    def live(name: str) -> List[_Candidate]:
        return [c for c in candidates[name] if not _overlaps(c.span, claimed)]

    def rank(candidate: _Candidate) -> Tuple[bool, int]:
        return (candidate.keyword_first != keyword_style, candidate.span[0])

    while True:
        open_fields = [f.name for f in fields if f.name not in values and live(f.name)]
        if not open_fields:
            return values
        choice = None
        for name in open_fields:
            rivals = [c.span for other in open_fields if other != name for c in live(other)]
            own = [c for c in live(name) if not _overlaps(c.span, rivals)]
            if own:
                choice = min(own, key=rank)
                break
        if choice is None:
            choice = min(live(open_fields[0]), key=rank)
        values[choice.field] = choice.value
        claimed.append(choice.span)
        if spans is not None:
            spans[choice.field] = choice.span


def _years(text: str) -> Optional[int]:
    for pattern in _YEARS_PATTERNS:
        match = re.search(pattern, text)
        if match:
            count = match.group("count")
            return _NUMBER_WORDS[count] if count in _NUMBER_WORDS else int(count)
    return None


def _currency(text: str) -> str:
    match = re.search(r"[$£€¥₹]", text)
    return match.group(0) if match else ""


def _money(value: float, currency: str = "") -> str:
    digits = f"{abs(value):,.0f}" if abs(value) >= 1e6 else f"{abs(value):,.2f}"
    sign = "-" if value < 0 and digits.strip("0.,") else ""
    return f"{sign}{currency}{digits}"


def _fixed(value: float, decimals: int = 2) -> str:
    """Fixed-point text with thousands separators, never "-0.00"."""
    text = f"{value:,.{decimals}f}"
    return text[1:] if text.startswith("-") and not text.strip("-0.,") else text


def _percent(fraction: float, decimals: int = 2) -> str:
    return f"{_fixed(fraction * 100, decimals)}%"


def _rate_text(fraction: float) -> str:
    """A rate as typed, without trailing zeros: 0.035 -> '3.5%'."""
    text = f"{fraction * 100:.4f}".rstrip("0").rstrip(".")
    return f"{'0' if text in ('', '-0') else text}%"


def _plain(value: float) -> str:
    return _fixed(value, 4 if value != 0 and abs(value) < 1 else 2)


def _reply(
    headline: str, results: Sequence[str] = (), assumptions: Sequence[str] = ()
) -> str:
    lines = [headline]
    lines.extend(f"- {line}" for line in results)
    if assumptions:
        lines.append("Assumptions:")
        lines.extend(f"- {line}" for line in assumptions)
    lines.extend((DISCLAIMER, CREDIT))
    return "\n".join(lines)


_TOKEN = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)%?"
_SINGLE_TOKEN = re.compile(_TOKEN)
_THOUSANDS_TOKEN = re.compile(r"[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?")
_JOINED_TOKEN = re.compile(_TOKEN + r"(?:," + _TOKEN + r")+")
_SERIES_MARK = re.compile(r"\b(?:of|for|on)\b|:")
# Settings that can sit inside a typed series and must not be read as data.
_SETTING_PHRASES = re.compile(
    r"^\s*\([\d\s.,]*\)"
    r"|^\s*\d+\s*/\s*\d+\s*/\s*\d+"
    r"|\b(?:period|window|length|lookback|span)\s*(?:of|=|:)?\s*\d+"
    r"|\b\d+[- ]?(?:day|period|bar|session)s?\b"
    r"|\bk\s*=\s*\d+(?:\.\d+)?"
    r"|\b(?:multiple|mult|width)\s*(?:of|=|:)?\s*\d+(?:\.\d+)?"
    r"|\b\d+(?:\.\d+)?\s*(?:standard\s+deviations?|std\.?\s*devs?|stdevs?|stds?"
    r"|sds?|sigmas?)\b"
    r"|\b(?:risk[- ]?free(?:\s+rate)?|rf)\s*(?:of|=|:|at)?\s*-?\d+(?:\.\d+)?\s*%?"
    r"|\b(?:at\s+)?\d+(?:\.\d+)?\s*%\s*(?:confidence|level|var\b|value\s+at\s+risk"
    r"|cvar|es\b|expected\s+shortfall)"
    r"|\bconfidence(?:\s+level)?\s*(?:of|=|:|at)?\s*\d+(?:\.\d+)?\s*%?"
    r"|\b(?:var|value\s+at\s+risk|expected\s+shortfall|cvar)\s+(?:at\s+)?\d+(?:\.\d+)?\s*%"
    r"|\b\d+\s+periods?\s+(?:a|per)\s+year\b"
)


def _series_text(text: str, start: int) -> str:
    """The part of ``text`` after ``start`` that holds the typed series.

    The series follows the first "of", "for", "on" or ":" after the keyword,
    unless that word only comes after the numbers themselves.
    """
    rest = text[start:]
    mark = _SERIES_MARK.search(rest)
    if mark and len(re.findall(r"\d+(?:\.\d+)?", rest[: mark.start()])) <= 3:
        after = rest[mark.end():]
        if re.search(r"\d", after):
            rest = after
    return _SETTING_PHRASES.sub(" ", rest)


# Words that may sit between the values of one typed series.
_SERIES_JOINERS = frozenset(("and", "then", "&", "->", "→", "%", "percent", "per", "cent", "pct"))


class _SplitSeries(ValueError):
    """The typed numbers sit in separate groups, so the series is unclear."""

    def __init__(self, groups: Sequence[Sequence[str]]) -> None:
        shown = " | ".join(", ".join(group) for group in groups)
        super().__init__(
            f"those numbers are in {len(groups)} separate groups ({shown}), so I can't "
            "tell which are the series; type the series as one list, like 100, 120, 90, 130"
        )


def _parse_series(segment: str) -> Tuple[List[float], bool, List[str]]:
    """Numbers typed in a series, whether they were percents, and numbers left out.

    Accepts spaces, semicolons or ", " between values, a single comma-joined
    run such as "10,11,12", and thousands separators such as "1,250.5".
    Values may be joined by "and", "then" or percent words; any other word
    starts a new group ("20% over 5 years" is two groups). Of several groups,
    the longest is the series when it has 3+ values and more than twice as
    many as the rest together; otherwise ``_SplitSeries`` is raised.
    """
    groups: List[List[str]] = [[]]
    # "minus 2" may arrive as "- 2" after normalisation; keep the sign.
    segment = re.sub(r"(^|[,;(]\s*|\s)-\s+(?=[\d.])", r"\1-", segment)
    for raw in re.split(r"[\s;]+|,(?=\s)", segment):
        token = raw.strip("()[]{}\"'$£€¥₹").rstrip(",.?!:")
        if (
            _SINGLE_TOKEN.fullmatch(token)
            or _THOUSANDS_TOKEN.fullmatch(token)
            or _JOINED_TOKEN.fullmatch(token)
        ):
            groups[-1].append(token)
        elif token and token not in _SERIES_JOINERS and groups[-1]:
            groups.append([])
    groups = [group for group in groups if group]
    if not groups:
        return [], False, []
    tokens = max(groups, key=len)
    left_out = [token for group in groups if group is not tokens for token in group]
    if left_out and (len(tokens) < 3 or len(tokens) <= 2 * len(left_out)):
        raise _SplitSeries(groups)
    percent = bool(re.search(r"\b(?:percent|per\s*cent|pct)\b|\d\s+%", segment))
    values: List[float] = []
    for token in tokens:
        if len(tokens) > 1 and _THOUSANDS_TOKEN.fullmatch(token):
            parts = [token.replace(",", "")]
        else:
            parts = token.split(",")
        for part in parts:
            if part.endswith("%"):
                percent = True
                part = part[:-1]
            values.append(float(part))
    return values, percent, left_out


def _trim(value: float) -> str:
    """A typed number without trailing zeros: 150.0 -> '150', 1.25 -> '1.25'."""
    text = f"{value:,.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _problem(message: str) -> str:
    return "\n".join((message, DISCLAIMER, CREDIT))


# ------------------------------------------------------- valuation requests

_FCF_WORDS = r"(?:base\s+)?(?:free\s+cash\s+flows?|fcf|cash\s+flows?)"
_DISCOUNT_WORDS = (
    r"(?:discount(?:ed)?(?:\s+rate)?|wacc|cost\s+of\s+(?:capital|equity)"
    r"|required\s+(?:rate\s+of\s+)?return|hurdle(?:\s+rate)?)"
)
_TERMINAL_WORDS = r"(?:terminal|perpetual|perpetuity|long[- ]term)(?:\s+growth)?(?:\s+rate)?"
_GROWTH_WORDS = (
    r"(?<!terminal )(?<!perpetual )(?<!perpetuity )(?<!long-term )"
    r"(?<!long term )(?<!dividend )(?<!price )\bgrow(?:th|ing|s)?\b(?:\s+rate)?"
)
_MULTIPLE_MARK = r"\s*(?:x\b|times\b|\*)"

_CAPM_FIELDS = (
    _Field(
        "beta",
        (r"\bbeta\b" + _FILL + _NUMBER_VALUE + r"(?!" + _PCT + r")",),
        (_NUMBER_VALUE + r"\s+beta\b",),
        "number",
    ),
    _Field(
        "risk_free",
        (r"\b(?:risk[- ]?free(?:\s+rate)?|rf)\b" + _FILL + _RATE,),
        (_PCT_VALUE + r"\s*risk[- ]?free\b",),
    ),
    _Field(
        "premium",
        (r"\b(?:(?:equity|market)\s+)?risk\s+premium\b" + _FILL + _RATE,
         r"\b(?:erp|mrp)\b" + _FILL + _RATE),
        (_PCT_VALUE + r"\s*(?:(?:equity|market)\s+)?risk\s+premium\b",),
    ),
    _Field(
        "market_return",
        (r"\b(?:expected\s+)?market\s+return\b" + _FILL + _RATE,),
        (_PCT_VALUE + r"\s*(?:expected\s+)?market\s+return\b",),
    ),
)

_DCF_FIELDS = (
    _Field(
        "fcf",
        (r"\b" + _FCF_WORDS + r"\b" + _FILL + _AMOUNT,),
        (_AMOUNT + r"\s*(?:(?:of|in)\s+)?" + _FCF_WORDS + r"\b",),
        "amount",
    ),
    _Field(
        "growth",
        (_GROWTH_WORDS + _FILL + _RATE,),
        (_PCT_VALUE + r"\s*(?:(?:annual|yearly|fcf|cash\s+flow)\s+)*growth\b",),
    ),
    _Field(
        "discount",
        (r"\b" + _DISCOUNT_WORDS + r"\b" + _FILL + _RATE,),
        (_PCT_VALUE + r"\s*" + _DISCOUNT_WORDS + r"\b",),
    ),
    _Field(
        "terminal",
        (r"\b" + _TERMINAL_WORDS + r"\b" + _FILL + _RATE,),
        (_PCT_VALUE + r"\s*" + _TERMINAL_WORDS + r"\b",),
    ),
    _Field(
        "multiple",
        (
            r"\b(?:exit|terminal)\s+(?:fcf\s+)?multiple\b" + _FILL + _NUMBER_VALUE
            + r"(?:" + _MULTIPLE_MARK + r")?(?!" + _PCT + r")",
            r"\b(?:exit|terminal)\b" + _FILL + _NUMBER_VALUE + _MULTIPLE_MARK,
        ),
        (_NUMBER_VALUE + _MULTIPLE_MARK + r"\s*(?:fcf\s+)?(?:exit|terminal)\b",),
        "number",
    ),
    _Field(
        "shares",
        (
            r"\b(?:shares(?:\s+outstanding|\s+in\s+issue)?|share\s+count"
            r"|diluted\s+shares)\b" + _FILL + _AMOUNT,
        ),
        (_AMOUNT + r"\s*(?:(?:diluted|outstanding)\s+)?shares\b",),
        "amount",
    ),
    _Field(
        "net_debt",
        (r"\bnet\s+debt\b" + _FILL + _AMOUNT,),
        (_AMOUNT + r"\s*(?:(?:of|in)\s+)?net\s+debt\b",),
        "amount",
    ),
    _Field(
        "net_cash",
        (r"\bnet\s+cash\b" + _FILL + _AMOUNT,),
        (_AMOUNT + r"\s*(?:(?:of|in)\s+)?net\s+cash\b",),
        "amount",
    ),
    _Field(
        "debt",
        (r"(?<!net )\b(?:total\s+)?debt\b" + _FILL + _AMOUNT,),
        (_AMOUNT + r"\s*(?:(?:of|in)\s+)?(?:total\s+)?debt\b",),
        "amount",
    ),
    _Field(
        "cash",
        (r"(?<!net )(?<!free )\bcash\b(?!\s+flows?)" + _FILL + _AMOUNT,),
        (_AMOUNT + r"\s*(?:(?:of|in)\s+)?cash\b(?!\s+flows?)",),
        "amount",
    ),
    _Field(
        "price",
        (
            r"\b(?:(?:current|share|stock|market)\s+)?price\b" + _FILL + _AMOUNT,
            r"\btrad(?:ing|es)\s+at" + _FILL + _AMOUNT,
        ),
        (_AMOUNT + r"\s*(?:a|per)\s+share\b",),
        "amount",
    ),
) + _CAPM_FIELDS

_DCF_INTENT = re.compile(
    r"\bdcf\b|\bdiscounted[- ]cash[- ]flows?\b|\bintrinsic\s+value\b|\bfair\s+value\b"
)
_FCF_MENTION = re.compile(r"\b(?:free\s+cash\s+flows?|fcf)\b")
_RATE_MENTION = re.compile(r"\b(?:discount(?:ed)?|wacc|beta)\b")
_CAPM_INTENT = re.compile(
    r"\bcost\s+of\s+equity\b|\bcapm\b|\bcapital\s+asset\s+pricing\b"
    r"|\brequired\s+(?:rate\s+of\s+)?return\b|\bexpected\s+return\b"
)
_FIB_INTENT = re.compile(
    r"\bfib(?:onacci)?\s+(?:retracements?|levels?|lines?|ratios?)\b"
    r"|\bretracement\s+levels?\b"
)


def _unused_rates(found: Dict[str, float]) -> Optional[str]:
    """A note on typed CAPM rates, which the project's estimate can't take."""
    typed = [
        f"{label} of {_rate_text(found[name])}"
        for name, label in (
            ("risk_free", "risk-free rate"),
            ("premium", "equity risk premium"),
            ("market_return", "market return"),
        )
        if name in found
    ]
    if not typed:
        return None
    listed = typed[0] if len(typed) == 1 else ", ".join(typed[:-1]) + " and " + typed[-1]
    verb = "was" if len(typed) == 1 else "were"
    return f"The {listed} you gave {verb} not used: {PROJECT}'s CAPM has its own rates."


def _net_debt(found: Dict[str, float], cash) -> Tuple[float, str]:
    if "net_debt" in found:
        value = found["net_debt"]
        return value, f"Net debt of {cash(value)} is subtracted to reach equity value."
    if "net_cash" in found:
        value = found["net_cash"]
        return -value, f"Net cash of {cash(value)} is added to reach equity value."
    if "debt" in found or "cash" in found:
        debt = found.get("debt", 0.0)
        held = found.get("cash", 0.0)
        return debt - held, (
            f"Debt of {cash(debt)} less cash of {cash(held)} is taken off to reach "
            "equity value."
        )
    return 0.0, "No net debt was given, so equity value equals enterprise value."


@dataclass(frozen=True)
class _Valuation:
    """What a reply uses from one run of the project's DCF model."""

    years: int
    pv_of_forecast: float
    terminal_value: Optional[float]
    pv_of_terminal_value: Optional[float]
    enterprise_value: Optional[float]
    equity_value: Optional[float]
    value_per_share: Optional[float]
    upside_percent: Optional[float]


def _valuation(data: Any, key: str) -> _Valuation:
    result = data.get(key) if isinstance(data, dict) else None
    if not isinstance(result, dict):
        raise _unusable(key)
    valuation = _Valuation(
        len(_rows(result, "years")),
        _number(result, "pvOfForecast"),
        _optional(result, "terminalValue"),
        _optional(result, "pvOfTerminalValue"),
        _optional(result, "enterpriseValue"),
        _optional(result, "equityValue"),
        _optional(result, "valuePerShare"),
        _optional(result, "upsidePercent"),
    )
    if valuation.terminal_value is not None and None in (
        valuation.pv_of_terminal_value,
        valuation.enterprise_value,
        valuation.equity_value,
    ):
        raise _unusable(key)
    return valuation


_ABOVE_ZERO = (("shares", "share count"), ("price", "share price"), ("multiple", "exit multiple"))


def _solve_dcf(text: str) -> Optional[str]:
    if not (
        _DCF_INTENT.search(text)
        or (_FCF_MENTION.search(text) and _RATE_MENTION.search(text))
    ):
        return None
    found = _read_fields(text, _DCF_FIELDS)
    base = found.get("fcf")
    if base is None or ("discount" not in found and "beta" not in found):
        return None
    typed_years = _years(text)
    if typed_years is not None and not 1 <= typed_years <= _MAX_DCF_YEARS:
        raise ValueError(f"the forecast must run for 1 to {_MAX_DCF_YEARS} years")
    if found.get("growth", 0.0) <= -1 or found.get("discount", 0.0) <= -1:
        raise ValueError("growth and discount rates must be above -100%")
    for name, label in _ABOVE_ZERO:
        if found.get(name, 1.0) <= 0:
            raise ValueError(f"the {label} must be above zero")
    currency = _currency(text)

    def cash(value: float) -> str:
        return _money(value, currency)

    growth = found.get("growth", 0.0)
    typed_discount = found.get("discount")
    terminal = found.get("terminal")
    multiple = found.get("multiple")
    shares = found.get("shares")
    price = found.get("price")
    net_debt, debt_note = _net_debt(found, cash)
    data = _ask(
        "dcf",
        {
            "fcf": base,
            "growth": growth,
            "years": typed_years,
            "discount": typed_discount,
            "beta": found.get("beta") if typed_discount is None else None,
            "terminalGrowth": terminal,
            "exitMultiple": multiple,
            "netDebt": net_debt,
            "shares": shares,
            "price": price,
        },
    )
    value = _valuation(data, "value")
    discount = _number(data, "discountRate")
    terminal_rate = _number(data, "terminalGrowth")
    years = value.years
    assumptions = [
        f"Free cash flow of {cash(base)} grows {_rate_text(growth)} a year for "
        f"{_plural(years, 'year')}"
        + (f" ({PROJECT}'s default)" if typed_years is None else "")
        + "; each year is discounted from its end."
    ]
    if "growth" not in found:
        assumptions.append("No growth rate was given, so cash flow stays flat (0%).")
    assumptions.append(
        f"{PROJECT}'s model starts from revenue, so the free cash flow stands in for "
        "it at a 100% margin with nothing else taken off."
    )
    if typed_discount is not None:
        assumptions.append(f"Discount rate {_rate_text(typed_discount)}, as given.")
        if "beta" in found:
            assumptions.append("The beta was ignored because a discount rate was given.")
    else:
        assumptions.append(
            f"Discount rate {_percent(discount)} from {PROJECT}'s CAPM estimate: "
            f"{_rate_text(_number(data, 'riskFreeRate'))} + {_trim(found['beta'])} x "
            f"{_rate_text(_number(data, 'equityRiskPremium'))}. It uses the cost of "
            "equity alone and ignores debt."
        )
        unused = _unused_rates(found)
        if unused:
            assumptions.append(
                f'{unused} Give a discount rate, e.g. "discount 9%", to use your own.'
            )
    if value.terminal_value is None:
        if multiple is not None:
            raise _unusable("value")
        return _problem(
            f"{PROJECT} has no terminal value for a {_rate_text(discount)} discount rate "
            f"with {_rate_text(terminal_rate)} terminal growth: a growing perpetuity needs "
            "the discount rate above the growth rate. Raise the discount rate, lower "
            'terminal growth or give an exit multiple such as "exit multiple 12x".'
        )
    if multiple is not None:
        assumptions.append(
            f"Terminal value: {_trim(multiple)}x final-year free cash flow as an exit "
            f"multiple ({PROJECT} applies it to EBITDA, which is that cash flow here)."
        )
    else:
        assumptions.append(
            f"Terminal value: cash flow grows {_rate_text(terminal_rate)} a year forever "
            f"after year {years}"
            + (f", {PROJECT}'s default rate." if terminal is None else ".")
        )
    assumptions.append(debt_note)
    results = [
        f"Present value of {_plural(years, 'year')} of free cash flow: "
        f"{cash(value.pv_of_forecast)}",
        f"Terminal value: {cash(value.terminal_value)}, worth "
        f"{cash(value.pv_of_terminal_value)} today",
        f"Enterprise value: {cash(value.enterprise_value)}",
        f"Equity value: {cash(value.equity_value)}",
    ]
    if value.value_per_share is not None and shares is not None:
        results.append(
            f"Value per share: {cash(value.value_per_share)} on {shares:,.0f} shares"
        )
        headline = f"DCF value: {cash(value.value_per_share)} a share"
    else:
        headline = f"DCF equity value: {cash(value.equity_value)}"
        assumptions.append('Add shares outstanding (e.g. "50m shares") for a value per share.')
    if value.upside_percent is not None and price is not None:
        side = "upside" if value.upside_percent >= 0 else "downside"
        results.append(
            f"Implied {side} against the {cash(price)} price: {value.upside_percent:+.2f}%"
        )
    if 0 < value.pv_of_forecast < value.pv_of_terminal_value:
        results.append(
            "Most of the value comes from beyond the forecast, so small changes to "
            "terminal growth or the discount rate move the result a lot"
        )
    if multiple is not None and terminal is not None:
        other = _valuation(data, "perpetuity")
        if other.terminal_value is not None:
            if other.value_per_share is not None:
                compare = f"{cash(other.value_per_share)} a share"
            else:
                compare = f"an equity value of {cash(other.equity_value)}"
            results.append(
                f"For comparison, a {_rate_text(terminal)} growing perpetuity gives {compare}"
            )
    if base < 0:
        results.append(
            "Free cash flow is negative, so the model value is negative too; a DCF "
            "suits businesses with positive, fairly steady cash flow"
        )
    return _reply(headline, results, assumptions)


def _solve_capm(text: str) -> Optional[str]:
    if not _CAPM_INTENT.search(text):
        return None
    found = _read_fields(text, _CAPM_FIELDS)
    if "beta" not in found:
        return None
    beta = found["beta"]
    data = _ask("capm", {"beta": beta})
    cost = _number(data, "costOfEquity")
    results = [
        f"Risk-free {_rate_text(_number(data, 'riskFreeRate'))} + beta {_trim(beta)} x "
        f"equity risk premium {_rate_text(_number(data, 'equityRiskPremium'))} = "
        f"{_percent(cost)}"
    ]
    if beta < 0:
        results.append(
            "A negative beta means the stock tends to move against the market, so "
            "CAPM asks for less than the risk-free rate"
        )
    assumptions = [f"The risk-free rate and equity risk premium are {PROJECT}'s own."]
    unused = _unused_rates(found)
    if unused:
        assumptions.append(unused)
    assumptions.append(
        f"CAPM prices only market (beta) risk. {PROJECT} uses it as the DCF discount "
        "rate, which ignores debt; a full WACC also weighs the after-tax cost of debt."
    )
    return _reply(f"Cost of equity (CAPM): {_percent(cost)}", results, assumptions)


def _solve_fibonacci(text: str) -> Optional[str]:
    intent = _FIB_INTENT.search(text)
    if not intent:
        return None
    low = _number_after(text, r"\b(?:swing\s+)?low\b")
    high = _number_after(text, r"\b(?:swing\s+)?high\b")
    if low is None or high is None:
        numbers = [float(n.replace(",", "")) for n in re.findall(_NUM, text[intent.end():])]
        if len(numbers) < 2:
            return None
        low, high = numbers[0], numbers[1]
    low, high = min(low, high), max(low, high)
    if low == high:
        return _problem("Fibonacci levels need a high and a low that differ.")
    levels = _ask("fibonacci", {"low": low, "high": high})
    if (
        not isinstance(levels, list)
        or not levels
        or not all(
            isinstance(level, dict)
            and isinstance(level.get("label"), str)
            and _is_number(level.get("value"))
            for level in levels
        )
    ):
        raise _unusable("levels")
    return _reply(
        f"Fibonacci retracements from {_trim(high)} down to {_trim(low)}:",
        [f"{level['label']}: {_fixed(level['value'])}" for level in levels],
        (
            f"{PROJECT} lists the levels from the high down to the low; each marks a "
            "pullback from the high of that share of the move.",
            "Traders watch them as possible support or resistance; they are a "
            "convention, not a forecast.",
        ),
    )


# ------------------------------------------------------ technicals requests

_INDICATOR = re.compile(
    r"\b(?:exponential\s+moving\s+averages?|simple\s+moving\s+averages?"
    r"|moving\s+averages?|relative\s+strength(?:\s+index)?|rsi|sma|ema|macd"
    r"|bollinger(?:\s+bands?)?|technical\s+(?:indicators?|analysis|readings?|signals?)"
    r"|technicals)\b"
)
_INDICATOR_NAMES = {
    "sma": r"(?:simple\s+moving\s+averages?|(?<!exponential )moving\s+averages?|sma)",
    "ema": r"(?:exponential\s+moving\s+averages?|ema)",
    "rsi": r"(?:relative\s+strength(?:\s+index)?|rsi)",
    "bollinger": r"(?:bollinger(?:\s+bands?)?)",
}
_ALL_INDICATORS = ("sma", "ema", "rsi", "macd", "bollinger")
_MACD_SETTINGS = re.compile(
    r"\bmacd\s*\(?\s*(?P<fast>\d+)\s*[,/]\s*(?P<slow>\d+)\s*[,/]\s*(?P<signal>\d+)"
)
_BOLLINGER_SETTINGS = re.compile(
    r"\bbollinger(?:\s+bands?)?\s*\(\s*(?P<n>\d+)(?:\s*,\s*(?P<k>\d+(?:\.\d+)?))?\s*\)"
)
_BOLLINGER_MULTIPLES = (
    r"\b(?P<k>\d+(?:\.\d+)?)\s*(?:standard\s+deviations?|std\.?\s*devs?|stdevs?|stds?"
    r"|sds?|sigmas?)\b",
    r"\bk\s*=\s*(?P<k>\d+(?:\.\d+)?)",
    r"\b(?:multiple|mult|width)\s*(?:of|=|:)?\s*(?P<k>\d+(?:\.\d+)?)",
)

_Report = Tuple[List[str], List[str], Optional[str]]


def _indicator_kind(name: str) -> str:
    if name.startswith(("exponential", "ema")):
        return "ema"
    if name.startswith(("simple", "moving", "sma")):
        return "sma"
    if name.startswith(("relative", "rsi")):
        return "rsi"
    if name.startswith(("macd", "bollinger")):
        return name.split()[0]
    return "all"


def _indicator_period(text: str, kind: str, only: bool) -> Optional[int]:
    """A period written next to the indicator: "rsi(10)", "10-day rsi"."""
    names = _INDICATOR_NAMES[kind]
    patterns = [
        names + r"\s*\(\s*(?P<n>\d+)",
        names + r"\s+(?P<n>\d+)(?=\s*(?:\b(?:of|for|on)\b|[:(]|$))",
        r"\b(?P<n>\d+)[- ]?(?:day|period|bar|week|month|session)s?\s+" + names,
        names + r"\s+(?:with\s+(?:an?\s+)?)?(?:period|window|length|lookback|span)"
        r"\s*(?:of|=|:)?\s*(?P<n>\d+)",
    ]
    if only:
        patterns.append(r"\b(?:period|window|length|lookback|span)\s*(?:of|=|:)?\s*(?P<n>\d+)")
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group("n"))
    return None


def _typed_series(
    text: str, starts: Sequence[int]
) -> Tuple[List[float], bool, List[str]]:
    """The series found from the first workable start, and any numbers left out."""
    split: Optional[_SplitSeries] = None
    for start in starts:
        try:
            values, percent, left_out = _parse_series(_series_text(text, start))
        except _SplitSeries as error:
            split = split or error
            continue
        if len(values) >= 2:
            return values, percent, left_out
    if split is not None:
        raise split
    return [], False, []


def _left_out_note(left_out: Sequence[str]) -> str:
    return f"Left out {', '.join(left_out)}, typed apart from the series."


def _at_least_one(value: int, name: str) -> int:
    if value < 1:
        raise ValueError(f"the {name} must be at least 1")
    return value


def _indicator_settings(
    text: str, kind: str, count: int, only: bool
) -> Tuple[Dict[str, Any], str, List[str]]:
    """What to ask the project for ``kind``: settings, a label and notes.

    A setting sent as ``None`` takes the project's default, and the label
    then shows no numbers for it.
    """
    if kind in ("sma", "ema"):
        label = kind.upper()
        period = _indicator_period(text, kind, only)
        notes: List[str] = []
        if period is None:
            period = count
            notes.append(f"No {label} period was given, so it uses all {count} values.")
        _at_least_one(period, f"{label} period")
        return {"period": period}, f"{label}({period})", notes
    if kind == "rsi":
        period = _indicator_period(text, kind, only)
        if period is None:
            return {"period": None}, "RSI", [
                f"No RSI period was given, so it uses {PROJECT}'s default."
            ]
        _at_least_one(period, "RSI period")
        return {"period": period}, f"RSI({period})", []
    if kind == "macd":
        typed = _MACD_SETTINGS.search(text)
        if not typed:
            return {"fast": None, "slow": None, "signal": None}, "MACD", [
                f"MACD uses {PROJECT}'s default periods."
            ]
        fast, slow, signal = (
            _at_least_one(int(typed.group(name)), "MACD period")
            for name in ("fast", "slow", "signal")
        )
        if fast >= slow:
            raise ValueError("the MACD fast period must be shorter than the slow period")
        return (
            {"fast": fast, "slow": slow, "signal": signal},
            f"MACD({fast},{slow},{signal})",
            [],
        )
    typed = _BOLLINGER_SETTINGS.search(text)
    period = int(typed.group("n")) if typed else _indicator_period(text, kind, only)
    multiple = float(typed.group("k")) if typed and typed.group("k") else None
    if multiple is None:
        for pattern in _BOLLINGER_MULTIPLES:
            match = re.search(pattern, text)
            if match:
                multiple = float(match.group("k"))
                break
    if period is not None:
        _at_least_one(period, "Bollinger period")
    if multiple is not None and multiple <= 0:
        raise ValueError("the Bollinger band width must be above zero")
    defaults = [
        name for name, setting in (("period", period), ("width", multiple)) if setting is None
    ]
    notes = (
        [f"Bollinger bands use {PROJECT}'s default {' and '.join(defaults)}."] if defaults else []
    )
    if period is not None:
        label = f"Bollinger({period}" + (f", {_trim(multiple)})" if multiple is not None else ")")
    elif multiple is not None:
        label = f"Bollinger bands at {_trim(multiple)} standard deviations"
    else:
        label = "Bollinger bands"
    return {"period": period, "multiple": multiple}, label, notes


def _position(value: float, level: float) -> str:
    return "above" if value > level else "below" if value < level else "level with"


def _indicator_report(
    kind: str, label: str, settings: Dict[str, Any], data: Any, values: List[float]
) -> _Report:
    """Lines and notes for one indicator, or why there are too few values."""
    count = len(values)
    last = values[-1]
    defaulted = any(setting is None for setting in settings.values())
    short = (
        f"Not enough values for {label}"
        + (f" at {PROJECT}'s default settings" if defaulted else "")
        + f": you gave {count}."
    )
    if kind in ("sma", "ema"):
        series = _series(data, kind, count)
        latest = series[-1]
        if latest is None:
            return [], [], short
        lines = [
            f"{label}: {_plain(latest)}; the latest value {_plain(last)} is "
            f"{_position(last, latest)} it"
        ]
        defined = [value for value in series if value is not None]
        if 1 < len(defined) <= 10:
            lines.append(f"{label} series: " + ", ".join(_plain(v) for v in defined))
        if kind == "sma":
            note = f"{label} is the plain average of the last {settings['period']} values."
        elif len(defined) > 1:
            note = (
                f"{label} is a moving average that gives recent values more weight than "
                "older ones."
            )
        else:
            note = (
                f"{label} has a single reading, the plain average of all {count} values; "
                "a shorter period gives recent values more weight."
            )
        return lines, [note], None
    if kind == "rsi":
        latest = _series(data, kind, count)[-1]
        if latest is None:
            return [], [], short
        return [f"{label}: {_fixed(latest)}"], [
            "RSI runs from 0 to 100; high readings are often called overbought and low "
            "ones oversold, which describes a tendency, not a forecast."
        ], None
    if kind == "macd":
        result = data.get("macd") if isinstance(data, dict) else None
        line, signal, histogram = (
            _series(result, name, count)[-1] for name in ("macd", "signal", "histogram")
        )
        if line is None:
            return [], [], short
        if signal is None or histogram is None:
            text_line = (
                f"{label} line: {_plain(line)}; there are too few values for its "
                "signal line yet"
            )
        else:
            text_line = (
                f"{label}: line {_plain(line)}, signal {_plain(signal)}, histogram "
                f"{_plain(histogram)}; the line is {_position(line, signal)} the signal"
            )
        return [text_line], [
            "MACD is a fast EMA minus a slow EMA; the signal line is an EMA of the "
            "MACD line, and the histogram is the gap between the two."
        ], None
    bands = data.get("bollinger") if isinstance(data, dict) else None
    upper, middle, lower = (
        _series(bands, name, count)[-1] for name in ("upper", "middle", "lower")
    )
    if upper is None or middle is None or lower is None:
        return [], [], short
    if last > upper:
        reading = "above the upper band, often read as stretched to the upside"
    elif last < lower:
        reading = "below the lower band, often read as stretched to the downside"
    else:
        reading = "inside the bands"
    return [
        f"{label}: upper {_plain(upper)}, middle {_plain(middle)}, lower "
        f"{_plain(lower)}; the latest value {_plain(last)} is {reading}"
    ], [
        "The middle band is a moving average; the outer bands sit a set number of "
        "standard deviations above and below it."
    ], None


def _solve_technicals(text: str) -> Optional[str]:
    mentions = list(_INDICATOR.finditer(text))
    if not mentions:
        return None
    kinds: List[str] = []
    for mention in mentions:
        kind = _indicator_kind(mention.group(0))
        for item in _ALL_INDICATORS if kind == "all" else (kind,):
            if item not in kinds:
                kinds.append(item)
    values, _, left_out = _typed_series(text, (mentions[-1].end(), mentions[0].end()))
    if len(values) < 2:
        return None
    only = len(kinds) == 1
    asked = {kind: _indicator_settings(text, kind, len(values), only) for kind in kinds}
    payload: Dict[str, Any] = {"values": values}
    payload.update((kind, settings) for kind, (settings, _, _) in asked.items())
    data = _ask("technicals", payload)
    lines: List[str] = []
    notes: List[str] = []
    missing: List[str] = []
    for kind, (settings, label, defaults) in asked.items():
        found, explained, short = _indicator_report(kind, label, settings, data, values)
        if short:
            missing.append(short)
            continue
        lines.extend(found)
        notes.extend(defaults)
        notes.extend(explained)
    if not lines:
        return _problem(" ".join(missing) + " Add more values or choose a shorter period.")
    notes.insert(0, "Values are read oldest first, as closing prices.")
    if left_out:
        notes.insert(1, _left_out_note(left_out))
    if missing:
        notes.append("Skipped: " + " ".join(missing))
    if only:
        return _reply(lines[0], lines[1:], notes)
    headline = (
        f"Technical readings for the {len(values)} values you typed "
        f"(latest {_plain(values[-1])}):"
    )
    return _reply(headline, lines, notes)


# ------------------------------------------------------------ risk requests

_RISK_INTENT = re.compile(
    r"\b(?:annuali[sz]ed\s+(?:return|volatility)|volatility|value\s+at\s+risk|var"
    r"|expected\s+shortfall|c-?var|conditional\s+var|(?:max(?:imum)?\s+)?draw[- ]?downs?"
    r"|sharpe(?:\s+ratio)?|skew(?:ness)?|kurtosis|t[- ]?stat(?:istic)?s?"
    r"|(?:return|risk)\s+(?:stats|statistics|metrics))\b"
)
_PRICE_WORDS = re.compile(r"\b(?:prices?|closes?|closing|navs?|quotes?)\b")
_RETURN_WORDS = re.compile(r"\breturns?\b")
_CONFIDENCE_PATTERNS = (
    r"(?P<value>\d+(?:\.\d+)?)\s*%\s*(?:confidence|level|var\b|value\s+at\s+risk|cvar"
    r"|es\b|expected\s+shortfall)",
    r"\bconfidence(?:\s+level)?\s*(?:of|=|:|at)?\s*(?P<value>\d+(?:\.\d+)?)\s*%?",
    r"\b(?:var|value\s+at\s+risk|expected\s+shortfall|cvar)\s+(?:at\s+)?"
    r"(?P<value>\d+(?:\.\d+)?)\s*%(?=\s*(?:\b(?:of|for|on)\b|:|$))",
)
_FREQUENCIES = (
    (r"\bdaily\b", "daily"),
    (r"\bweekly\b", "weekly"),
    (r"\bmonthly\b", "monthly"),
    (r"\bquarterly\b", "quarterly"),
    (
        r"\b(?:annual|yearly)\s+(?:returns?|prices?|closes?|data|values?|observations?)\b",
        "yearly",
    ),
)
_SHARPE = re.compile(r"\bsharpe\b")
_ANNUALISED_RETURN = re.compile(r"\bannuali[sz]ed\s+returns?\b")


def _risk_metric(name: str) -> str:
    name = " ".join(name.split())
    if "volatil" in name:
        return "volatility"
    if name.startswith(("value at risk", "var")):
        return "var"
    if name.startswith(("expected", "cvar", "c-var", "conditional")):
        return "es"
    if "draw" in name:
        return "drawdown"
    if name.startswith("sharpe"):
        return "sharpe"
    if name.startswith("skew"):
        return "skewness"
    if name == "kurtosis":
        return "kurtosis"
    if name.endswith("return"):
        return "return"
    if name.startswith("t") and "stat" in name and not name.startswith("stat"):
        return "t"
    return "stats"


def _frequency(text: str) -> Optional[str]:
    """How often the typed figures were taken, when the request says."""
    match = re.search(
        r"\b(?P<n>\d+)\s+(?:periods?|observations?|returns?)\s+(?:a|per)\s+year\b", text
    )
    if match and int(match.group("n")) > 0:
        return f"figures taken {int(match.group('n'))} times a year"
    for pattern, label in _FREQUENCIES:
        if re.search(pattern, text):
            return f"{label} figures"
    return None


def _confidence(text: str) -> Optional[float]:
    """A typed confidence level for VaR and expected shortfall, if any."""
    for pattern in _CONFIDENCE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            value = float(match.group("value"))
            level = value / 100 if value > 1 else value
            if not 0 < level < 1:
                raise ValueError("the confidence level must be between 0% and 100%")
            return level
    return None


def _solve_risk(text: str) -> Optional[str]:
    intent = _RISK_INTENT.search(text)
    if not intent:
        return None
    metric = _risk_metric(intent.group(0))
    if metric == "sharpe":
        if len(re.findall(_NUM, text)) < 2:
            return None
        return _problem(
            f"{PROJECT} has no Sharpe ratio calculation for numbers you type. For risk "
            'and return figures, try e.g. "return stats of 1%, -2%, 0.5%, 3%".'
        )
    raw, percent, left_out = _typed_series(text, (intent.end(), 0))
    if len(raw) < 2:
        return None
    # Skewness, kurtosis and t describe the typed numbers themselves unless
    # they are called prices.
    sample = metric in ("skewness", "kurtosis", "t", "stats")
    says_prices = bool(_PRICE_WORDS.search(text))
    prices = False
    if percent:
        values = [value / 100 for value in raw]
        reading = "Read the numbers as percent returns (1% = 0.01)."
    elif not says_prices and (sample or _RETURN_WORDS.search(text) or any(v < 0 for v in raw)):
        if any(abs(value) > 1 for value in raw):
            values = [value / 100 for value in raw]
            reading = (
                "Read the numbers as percent returns because some are bigger than 1; "
                "write 0.01 for 1% to use decimals."
            )
        else:
            values = list(raw)
            reading = (
                "Read the numbers as decimal returns (0.01 = 1%); add % signs if you "
                "meant percents."
            )
    else:
        if any(value <= 0 for value in raw):
            return _problem(
                'Prices must all be above zero; if these are returns, say "returns" '
                "or add % signs."
            )
        if len(raw) < 3:
            return _problem(
                f"I need at least 3 prices to measure risk; you gave {len(raw)}. If these "
                'are returns, say "returns" or add % signs.'
            )
        prices = True
        values = list(raw)
        reading = (
            f"Read the {len(raw)} numbers as prices, oldest first, giving "
            f'{len(raw) - 1} returns; say "returns" if they already are.'
        )
    frequency = _frequency(text)
    daily = frequency in (None, "daily figures")
    if metric in ("volatility", "return") and not daily:
        return _problem(
            f"{PROJECT} annualises figures as if they were daily, so it can't annualise "
            f'{frequency}. Ask for e.g. "value at risk" or "return stats" instead.'
        )
    if metric == "return" and not prices:
        return _problem(
            f"{PROJECT} works out an annualised return only from prices. Type them "
            'oldest first, e.g. "annualised return of prices 100, 104, 101, 108".'
        )
    confidence = _confidence(text)
    data = _ask("risk", {"values": values, "prices": prices, "confidence": confidence})
    count = _whole(data, "count")
    volatility = _number(data, "volatility")
    var = _number(data, "valueAtRisk")
    shortfall = _number(data, "expectedShortfall")
    drawdown = _number(data, "maxDrawdown")
    average = _number(data, "mean")
    middle = _number(data, "median")
    spread = _number(data, "stdDev")
    skew = _number(data, "skewness")
    kurt = _number(data, "kurtosis")
    t_stat = _optional(data, "tStatistic")
    annual = _number(data, "annualisedReturnPercent") if prices and daily else None
    level = "" if confidence is None else _rate_text(confidence)
    t_text = "n/a" if t_stat is None else _fixed(t_stat)

    metrics: Dict[str, str] = {}
    if annual is not None:
        metrics["return"] = f"Annualised return: {_fixed(annual)}%"
    if daily:
        metrics["volatility"] = f"Annualised volatility: {_percent(volatility)}"
    metrics["var"] = f"Historical {level + ' ' if level else ''}VaR: {_percent(var)} in one period"
    metrics["es"] = (
        f"Expected shortfall{f' ({level})' if level else ''}: {_percent(shortfall)}, "
        "the average loss in the worst cases"
    )
    metrics["drawdown"] = f"Max drawdown: {_percent(drawdown)}" + (
        "" if prices else " of the compounded returns"
    )
    headlines = {
        "skewness": f"Skewness: {_fixed(skew)}",
        "kurtosis": f"Excess kurtosis: {_fixed(kurt)}",
        "t": f"t-statistic: {t_text}",
        "stats": f"Return statistics for {count} returns:",
    }
    headline = metrics.pop(metric) if metric in metrics else headlines[metric]
    results = list(metrics.values()) + [
        f"Per period: mean {_percent(average)}, median {_percent(middle)}, "
        f"standard deviation {_percent(spread)}",
        f"Skewness {_fixed(skew)}, excess kurtosis {_fixed(kurt)}, t-statistic {t_text}",
    ]
    assumptions = [reading]
    if left_out:
        assumptions.append(_left_out_note(left_out))
    if frequency is None:
        assumptions.append(
            f"The figures are treated as daily, as {PROJECT}'s annualising assumes; say "
            '"monthly" or "weekly" if they are not.'
        )
    elif not daily:
        assumptions.append(
            f"{PROJECT} annualises only daily figures, so there is no annualised "
            f"volatility or return for {frequency}."
        )
    if annual is not None:
        assumptions.append(
            f"The annualised return is {PROJECT}'s: the average daily return scaled up "
            "to a year, without compounding."
        )
    assumptions.append(
        "VaR and expected shortfall are historical: they come from the returns "
        "themselves, with no distribution assumed."
    )
    if confidence is None:
        assumptions.append(
            f"VaR and expected shortfall use {PROJECT}'s default confidence level; "
            'say e.g. "99% VaR" to choose one.'
        )
    if metric in ("t", "stats"):
        assumptions.append(
            "The further the t-statistic is from zero, the less likely the average "
            "return is just noise."
        )
    if _SHARPE.search(text):
        assumptions.append(f"There is no Sharpe ratio: {PROJECT} has none for numbers you type.")
    if _ANNUALISED_RETURN.search(text) and annual is None:
        assumptions.append(
            f"There is no annualised return: {PROJECT} works one out only from daily prices."
        )
    return _reply(headline, results, assumptions)


# ------------------------------------------------------------ DRIP requests

_DRIP_INTENT = re.compile(
    r"\bdrip\b|\bdividend\s+reinvest\w*"
    r"|\breinvest(?:ing|ed|ment)?\s+(?:(?:the|my|all|of|your)\s+)*dividends?\b"
    r"|\bdividend\s+snowball\b"
)
_NO_REINVEST = re.compile(
    r"\b(?:without|no|not|don't|do\s+not|never)\s+(?:re-?invest\w*|drip)\b"
    r"|\bpaid\s+out\b|\bas\s+cash\b"
)
_CONTRIBUTION = re.compile(
    r"(?:(?:\b(?:add(?:ing|s)?|plus|contribut(?:e|es|ing|ions?)|deposit(?:s|ing)?"
    r"|top(?:ping)?\s+up(?:\s+by)?|with|and|then)\s+(?:of\s+)?|\+\s*)"
    r"(?:(?:another|an?\s+(?:extra|additional|further))\s+)?)?" + _AMOUNT
    + r"\s*(?:(?:a|per|each|every)\s+(?P<period>month|year)|(?P<adverb>monthly|yearly|annually))\b"
)
_CONTRIBUTION_NOUN = re.compile(
    r"\b(?P<adverb>monthly|yearly|annual)\s+(?:contributions?|deposits?|additions?"
    r"|top[- ]?ups?|savings?)" + _FILL + _AMOUNT
)
_DRIP_FIELDS = (
    _Field(
        "initial",
        (
            r"\b(?:drip|invest(?:ing|ed|ment)?|start(?:ing)?\s+(?:with|from|at)"
            r"|initial(?:\s+investment)?|principal|lump\s+sum|put(?:ting)?\s+in)\b"
            + _FILL + _AMOUNT,
        ),
        (_AMOUNT + r"\s*(?:initial\s+investment|lump\s+sum|invested|investment)\b",),
        "amount",
    ),
    _Field(
        "yield",
        (r"\b(?:(?:dividend|starting|initial|current)\s+)?yield(?:ing|s)?\b" + _FILL + _RATE,),
        (_PCT_VALUE + r"\s*(?:(?:starting|initial|dividend|div|current)\s+)*yield\b",),
        "percent",
    ),
    _Field(
        "dividend_growth",
        (
            r"\b(?:dividends?|div|payouts?)\s+(?:growth(?:\s+rate)?|grow(?:s|ing)?"
            r"|increases?|raises?|hikes?)\b" + _FILL + _RATE,
            r"(?<!price )(?<!capital )(?<!stock )(?<!share )\bgrow(?:th|s|ing)?\b"
            r"(?:\s+rate)?" + _FILL + _RATE,
        ),
        (
            _PCT_VALUE + r"\s*(?:(?:a\s+year|annual|yearly)\s+)?(?:dividend|div|payout)\s+"
            r"(?:growth|increases?|raises?|hikes?)\b",
        ),
    ),
    _Field(
        "price_growth",
        (
            r"\b(?:(?:share|stock)\s+)?(?:price|capital)\s+(?:growth|appreciation|gains?"
            r"|grows?|growing|rises?|increases?)\b" + _FILL + _RATE,
            r"\bappreciation\b" + _FILL + _RATE,
        ),
        (
            _PCT_VALUE + r"\s*(?:(?:a\s+year|annual|yearly)\s+)?(?:(?:share|stock)\s+)?"
            r"(?:price|capital)\s+(?:growth|appreciation|gains?)\b",
            _PCT_VALUE + r"\s*(?:(?:a\s+year|annual|yearly)\s+)?appreciation\b",
        ),
    ),
)


@dataclass(frozen=True)
class _DripYear:
    """One year of the project's DRIP simulation, as a reply uses it."""

    year: int
    dividend_income: float
    ending_value: float
    yield_on_cost: float


def _drip_years(data: Any, key: str, years: int) -> List[_DripYear]:
    rows = [
        _DripYear(
            _whole(row, "year"),
            _number(row, "dividendIncome"),
            _number(row, "endingValue"),
            _number(row, "yieldOnCost"),
        )
        for row in _rows(data, key)
    ]
    if len(rows) != years:
        raise _unusable(key)
    return rows


def _drip_horizons(data: Any, key: str) -> List[Tuple[int, float, float]]:
    return [
        (_whole(row, "horizon"), _number(row, "finalValue"), _number(row, "annualIncome"))
        for row in _rows(data, key)
    ]


def _solve_drip(text: str) -> Optional[str]:
    if not _DRIP_INTENT.search(text):
        return None
    taken: List[Tuple[int, int]] = []
    contribution = 0.0
    monthly: Optional[float] = None
    match = _CONTRIBUTION.search(text) or _CONTRIBUTION_NOUN.search(text)
    if match:
        amount = _amount(match)
        groups = match.groupdict()
        if groups.get("period") == "month" or groups.get("adverb") == "monthly":
            monthly = amount
            contribution = amount * 12
        else:
            contribution = amount
        taken.append(match.span("value"))
    spans: Dict[str, Tuple[int, int]] = {}
    found = _read_fields(text, _DRIP_FIELDS, taken, spans)
    initial = found.get("initial")
    if initial is None:
        used = taken + list(spans.values())
        for candidate in re.finditer(_AMOUNT, text):
            if not _overlaps(candidate.span("value"), used):
                initial = _amount(candidate)
                break
    if initial is None and contribution:
        initial = 0.0
    if initial is None or "yield" not in found:
        return None
    years = _years(text)
    if years is not None and years < 1:
        return _problem("A DRIP projection needs at least 1 year.")
    if years is not None and years > _MAX_DRIP_YEARS:
        raise ValueError(f"a DRIP projection can run for at most {_MAX_DRIP_YEARS} years")
    starting_yield = found["yield"]
    dividend_growth = found.get("dividend_growth", 0.0)
    price_growth = found.get("price_growth", 0.0)
    reinvest = not _NO_REINVEST.search(text)
    currency = _currency(text)

    def cash(value: float) -> str:
        return _money(value, currency)

    data = _ask(
        "drip",
        {
            "initialInvestment": initial,
            "annualContribution": contribution,
            "startingYieldPercent": starting_yield,
            "dividendGrowth": dividend_growth,
            "priceGrowth": price_growth,
            "years": years,
        },
    )
    chosen, other = ("reinvest", "payout") if reinvest else ("payout", "reinvest")
    start = cash(initial)
    if contribution:
        if monthly is not None:
            extra = f"{cash(monthly)} a month"
        else:
            extra = f"{cash(contribution)} a year"
        start = f"{start} plus {extra}" if initial else extra
    way = "with dividends reinvested" if reinvest else "with dividends paid out"
    if years is not None:
        rows = _drip_years(data, chosen, years)
        final = rows[-1].ending_value
        alternative = _drip_years(data, other, years)[-1].ending_value
        shown = rows if years <= 10 else [
            row for row in rows if row.year == 1 or row.year % 5 == 0 or row.year == years
        ]
        results = [
            f"Year {row.year}: dividends {cash(row.dividend_income)}, value "
            f"{cash(row.ending_value)}, yield on cost {_fixed(row.yield_on_cost)}%"
            for row in shown
        ]
        headline = (
            f"DRIP projection: {start} grows to {cash(final)} in "
            f"{_plural(years, 'year')} {way}"
        )
    else:
        horizons = _drip_horizons(data, chosen)
        alternative = _drip_horizons(data, other)[-1][1]
        results = [
            f"After {_plural(horizon, 'year')}: value {cash(value)}, dividends "
            f"{cash(income)} that year"
            for horizon, value, income in horizons
        ]
        headline = f"DRIP projection: {start} {way}:"
    if reinvest:
        results.append(
            f"Taking dividends as cash instead: value {cash(alternative)}, not counting "
            "the dividends paid out"
        )
    else:
        results.append(f"Reinvesting them instead would give {cash(alternative)}")
    if dividend_growth:
        yield_note = (
            f"The dividend yield on the current value starts at {_trim(starting_yield)}% "
            f"and grows {_rate_text(dividend_growth)} a year."
        )
    else:
        yield_note = (
            f"The dividend yield on the current value stays at {_trim(starting_yield)}%; "
            'add e.g. "4% dividend growth" to grow it.'
        )
    assumptions = [yield_note]
    if "price_growth" in found:
        assumptions.append(f"The share price grows {_rate_text(price_growth)} a year.")
    else:
        assumptions.append(
            'The share price stays flat; add e.g. "3% price growth" to change that.'
        )
    if monthly is not None:
        assumptions.append(
            f"{cash(monthly)} a month goes in as {cash(contribution)} at each year end."
        )
    elif contribution:
        assumptions.append(f"{cash(contribution)} goes in at each year end.")
    if years is None:
        assumptions.append(
            f"With no number of years given, these are the horizons {PROJECT} shows; "
            'add e.g. "for 15 years" for a year-by-year view.'
        )
    else:
        assumptions.append(
            "Yield on cost is the year's dividends divided by the money put in before "
            "that year."
        )
    assumptions.append("Taxes, fees and share rounding are ignored.")
    return _reply(headline, results, assumptions)


# ------------------------------------------------------------- entry points

_EXAMPLES = (
    "dcf with fcf 100m growth 8% discount 9% terminal 3% 50m shares net debt 200m",
    "cost of equity for beta 1.3",
    "rsi 5 of 44, 44.3, 44.1, 43.6, 44.5, 44.9, 45.2",
    "sma 5 of 10, 11, 12, 13, 14, 15",
    "bollinger(4, 1.5) of 10 11 12 11 13 14",
    "fibonacci levels between 100 and 150",
    "max drawdown of 100, 120, 90, 130",
    "value at risk of returns 1%, -2%, 0.5%, -3%, 2%",
    "drip 8000 at 3.5% yield 4% dividend growth for 12 years",
)


def solve(text: str) -> Optional[str]:
    """Answer an investment-maths request, or ``None`` if ``text`` isn't one.

    Handles DCF, CAPM, Fibonacci levels, technicals (SMA, EMA, RSI, MACD,
    Bollinger), risk and return statistics, and DRIP projections, using only
    the numbers in ``text``. ``None`` also means the needed numbers are missing.
    The figures come from Portfolio-Watcher, so a request it can answer raises
    :class:`jarvis.projects.ProjectUnavailable` when the project or Node.js
    is missing, and :class:`jarvis.projects.ProjectError` when it fails.
    """
    cleaned = _clean(text)
    try:
        for solver in (
            _solve_drip,
            _solve_dcf,
            _solve_capm,
            _solve_fibonacci,
            _solve_technicals,
            _solve_risk,
        ):
            reply = solver(cleaned)
            if reply is not None:
                return reply
    except (ValueError, ZeroDivisionError, OverflowError) as error:
        return _problem(f"I couldn't work that out: {error}.")
    return None


def usage() -> str:
    """How to ask, with examples; needs neither the project nor Node.js."""
    lines = [
        f"I can do investment maths with {PROJECT}'s calculations on numbers you type "
        "(no market data). Try:"
    ]
    lines.extend(f"- {example}" for example in _EXAMPLES)
    lines.extend((DISCLAIMER, CREDIT))
    return "\n".join(lines)
