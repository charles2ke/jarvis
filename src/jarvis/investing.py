"""Investment maths on numbers you type: DCF, CAPM, technicals, risk and DRIP.

Ported from Portfolio-Watcher by charles2ke
(https://github.com/charles2ke/Portfolio-Watcher) at commit
4dddc15734246445eedb7b040b0722bcbe49bc02, MIT licence, "Copyright (c) 2026
Charles Gomes". The formulas follow these files:

* ``src/research/dcf.ts``: ``terminalValuePerpetuity``, the discounting in
  ``valueDcf`` and the 4.2% risk-free rate and 5% equity risk premium.
* ``src/research/technicals.ts``: ``sma``, ``ema``, ``rsi`` (Wilder),
  ``macd``, ``bollinger`` and ``fibonacciLevels``.
* ``src/research/risk.ts``: ``annualisedVolatility``, ``historicalVar``,
  ``expectedShortfall`` and ``maxDrawdown``.
* ``src/research/quant.ts``: ``mean``, ``median``, ``stdDev``,
  ``skewness``, ``kurtosis`` and ``tStatistic``.
* ``src/research/dividends.ts``: ``simulateDrip``.
* ``src/research/universe.ts``: ``standardDeviation`` and ``dailyReturns``.

Deliberate differences from the original:

* The DCF starts from a free cash flow you type instead of
  Portfolio-Watcher's revenue and margin model, and it does not round each
  year's cash flow to cents, so results can differ from it by a few cents.
  An exit multiple applies to final-year free cash flow, not EV/EBITDA.
* ``sharpe_ratio`` subtracts a risk-free rate; ``sharpeLike`` does not.
* ``simulate_drip`` takes every rate as a fraction and returns unrounded
  rows, with yield on cost as a fraction rather than a rounded percent.
* A period below 1 raises ``ValueError`` instead of returning nonsense.

Nothing here fetches market data. :func:`solve` uses only the numbers in the
request, and every reply says it is general education, not advice.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "BollingerBands",
    "CREDIT",
    "DISCLAIMER",
    "DcfResult",
    "DcfYear",
    "DripYear",
    "MacdResult",
    "PROJECT",
    "REPO_URL",
    "SITE_URL",
    "TOPICS",
    "annualised_volatility",
    "bollinger",
    "capm_cost_of_equity",
    "dcf_value",
    "ema",
    "expected_shortfall",
    "fibonacci_levels",
    "historical_var",
    "kurtosis",
    "macd",
    "max_drawdown",
    "mean",
    "median",
    "rsi",
    "sharpe_ratio",
    "simple_returns",
    "simulate_drip",
    "skewness",
    "sma",
    "solve",
    "std_dev",
    "t_statistic",
    "terminal_value_perpetuity",
    "usage",
]

PROJECT = "Portfolio-Watcher"
SITE_URL = "https://charles2ke.github.io/Portfolio-Watcher/"
REPO_URL = "https://github.com/charles2ke/Portfolio-Watcher"
SOURCE_COMMIT = "4dddc15734246445eedb7b040b0722bcbe49bc02"
CREDIT = f"From {PROJECT}: {SITE_URL}"
DISCLAIMER = (
    "General education only, not investment advice — past performance and "
    "model outputs do not predict future returns."
)

RISK_FREE_RATE = 0.042
EQUITY_RISK_PREMIUM = 0.05
DEFAULT_TERMINAL_GROWTH = 0.025
FORECAST_YEARS = 5
MAX_DCF_YEARS = 50
DEFAULT_DRIP_YEARS = 10
MAX_DRIP_YEARS = 100
TRADING_DAYS_PER_YEAR = 252
DEFAULT_CONFIDENCE = 0.95
SIGNIFICANCE_T = 1.96
MIN_SIGNIFICANT_OBSERVATIONS = 20
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BOLLINGER_PERIOD = 20
BOLLINGER_MULTIPLE = 2.0
MOVING_AVERAGE_PERIOD = 20

FIBONACCI_RATIOS: Tuple[Tuple[str, float], ...] = (
    ("0%", 0.0),
    ("23.6%", 0.236),
    ("38.2%", 0.382),
    ("50%", 0.5),
    ("61.8%", 0.618),
    ("78.6%", 0.786),
    ("100%", 1.0),
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
    "Sharpe ratio",
    "Return statistics",
    "Dividend reinvestment (DRIP)",
)

Series = List[Optional[float]]


def round_to(value: float, decimals: int = 2) -> float:
    """Round half up like JavaScript's ``Math.round`` (PW's ``roundTo``)."""
    factor = 10 ** decimals
    return math.floor(value * factor + 0.5) / factor


def _total(values: Sequence[float]) -> float:
    # A plain left-to-right sum like JavaScript's reduce; Python 3.12's sum()
    # compensates rounding and would differ from the original in the last digit.
    total = 0.0
    for value in values:
        total += value
    return total


def _check_period(period: int, name: str = "period") -> None:
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError(f"the {name} must be a whole number of at least 1")


# ------------------------------------------------------------- technicals


def sma(values: Sequence[float], period: int) -> Series:
    """Simple moving average; ``None`` until a full window is available."""
    _check_period(period)
    out: Series = []
    for i in range(len(values)):
        if i < period - 1:
            out.append(None)
            continue
        total = 0.0
        for j in range(i - period + 1, i + 1):
            total += values[j]
        out.append(total / period)
    return out


def ema(values: Sequence[float], period: int) -> Series:
    """Exponential moving average seeded with the first window's SMA."""
    _check_period(period)
    out: Series = [None] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    running = 0.0
    for i in range(period):
        running += values[i]
    running /= period
    out[period - 1] = running
    for i in range(period, len(values)):
        running = values[i] * k + running * (1 - k)
        out[i] = running
    return out


def rsi(values: Sequence[float], period: int = RSI_PERIOD) -> Series:
    """Wilder's relative strength index (0-100); needs ``period + 1`` values."""
    _check_period(period)
    out: Series = [None] * len(values)
    if len(values) <= period:
        return out
    gain = 0.0
    loss = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        if change >= 0:
            gain += change
        else:
            loss -= change
    gain /= period
    loss /= period
    out[period] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        up = change if change > 0 else 0.0
        down = -change if change < 0 else 0.0
        gain = (gain * (period - 1) + up) / period
        loss = (loss * (period - 1) + down) / period
        out[i] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return out


@dataclass(frozen=True)
class MacdResult:
    """MACD line, signal line and histogram, aligned with the input."""

    macd: Tuple[Optional[float], ...]
    signal: Tuple[Optional[float], ...]
    histogram: Tuple[Optional[float], ...]


def macd(
    values: Sequence[float],
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> MacdResult:
    """Fast EMA minus slow EMA, its signal-line EMA and the histogram."""
    _check_period(signal, "signal period")
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    line: Series = [
        f - s if f is not None and s is not None else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    signal_line: Series = [None] * len(values)
    first = next((i for i, value in enumerate(line) if value is not None), -1)
    if first != -1:
        compact = [value for value in line[first:] if value is not None]
        for i, value in enumerate(ema(compact, signal)):
            if value is not None:
                signal_line[first + i] = value
    histogram = [
        m - s if m is not None and s is not None else None
        for m, s in zip(line, signal_line)
    ]
    return MacdResult(tuple(line), tuple(signal_line), tuple(histogram))


@dataclass(frozen=True)
class BollingerBands:
    """Upper, middle (SMA) and lower bands, aligned with the input."""

    upper: Tuple[Optional[float], ...]
    middle: Tuple[Optional[float], ...]
    lower: Tuple[Optional[float], ...]


def bollinger(
    values: Sequence[float],
    period: int = BOLLINGER_PERIOD,
    multiple: float = BOLLINGER_MULTIPLE,
) -> BollingerBands:
    """SMA plus/minus ``multiple`` population standard deviations."""
    middle = sma(values, period)
    upper: Series = []
    lower: Series = []
    for i, centre in enumerate(middle):
        if centre is None:
            upper.append(None)
            lower.append(None)
            continue
        variance = 0.0
        for j in range(i - period + 1, i + 1):
            variance += (values[j] - centre) ** 2
        sd = math.sqrt(variance / period)
        upper.append(centre + multiple * sd)
        lower.append(centre - multiple * sd)
    return BollingerBands(tuple(upper), tuple(middle), tuple(lower))


def fibonacci_levels(low: float, high: float) -> List[Tuple[str, float]]:
    """Retracement levels from ``high`` down to ``low``, rounded to cents."""
    span = high - low
    return [
        (label, round_to(high - span * ratio, 2)) for label, ratio in FIBONACCI_RATIOS
    ]


# ------------------------------------------------------ statistics and risk


def mean(values: Sequence[float]) -> float:
    """Arithmetic mean; 0 for an empty series."""
    if not values:
        return 0.0
    return _total(values) / len(values)


def median(values: Sequence[float]) -> float:
    """Median; 0 for an empty series."""
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 0:
        return (ordered[middle - 1] + ordered[middle]) / 2
    return ordered[middle]


def std_dev(values: Sequence[float]) -> float:
    """Sample standard deviation (divides by n - 1); 0 below two values."""
    if len(values) < 2:
        return 0.0
    centre = mean(values)
    return math.sqrt(_total([(v - centre) ** 2 for v in values]) / (len(values) - 1))


def _population_sd(values: Sequence[float], centre: float) -> float:
    return math.sqrt(_total([(v - centre) ** 2 for v in values]) / len(values))


def skewness(values: Sequence[float]) -> float:
    """Population skewness; 0 below three values or with no spread."""
    if len(values) < 3:
        return 0.0
    centre = mean(values)
    sd = _population_sd(values, centre)
    if sd == 0:
        return 0.0
    return _total([((v - centre) / sd) ** 3 for v in values]) / len(values)


def kurtosis(values: Sequence[float]) -> float:
    """Population excess kurtosis; 0 below four values or with no spread."""
    if len(values) < 4:
        return 0.0
    centre = mean(values)
    sd = _population_sd(values, centre)
    if sd == 0:
        return 0.0
    return _total([((v - centre) / sd) ** 4 for v in values]) / len(values) - 3


def t_statistic(values: Sequence[float]) -> Optional[float]:
    """One-sample t-statistic against a zero mean; ``None`` if undefined."""
    if len(values) < 3:
        return None
    sd = std_dev(values)
    if sd == 0:
        return None
    return mean(values) * math.sqrt(len(values)) / sd


def simple_returns(prices: Sequence[float]) -> List[float]:
    """Period-over-period returns as fractions, from prices above zero."""
    if any(price <= 0 for price in prices):
        raise ValueError("prices must all be above zero")
    return [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]


def annualised_volatility(
    returns: Sequence[float], periods_per_year: float = TRADING_DAYS_PER_YEAR
) -> float:
    """Sample standard deviation of returns scaled by sqrt(periods a year)."""
    return std_dev(returns) * math.sqrt(periods_per_year)


def _tail(returns: Sequence[float], confidence: float) -> List[float]:
    ordered = sorted(returns)
    cutoff = max(1, math.floor((1 - confidence) * len(ordered)))
    return ordered[:cutoff]


def _check_confidence(confidence: float) -> None:
    if not 0 < confidence < 1:
        raise ValueError("the confidence level must be between 0% and 100%")


def historical_var(returns: Sequence[float], confidence: float = DEFAULT_CONFIDENCE) -> float:
    """Historical value at risk as a positive loss fraction (0 if no loss)."""
    _check_confidence(confidence)
    if not returns:
        return 0.0
    quantile = _tail(returns, confidence)[-1]
    return -quantile if quantile < 0 else 0.0


def expected_shortfall(
    returns: Sequence[float], confidence: float = DEFAULT_CONFIDENCE
) -> float:
    """Average loss in the VaR tail as a positive fraction (0 if no loss)."""
    _check_confidence(confidence)
    if not returns:
        return 0.0
    tail = _tail(returns, confidence)
    average = _total(tail) / len(tail)
    return -average if average < 0 else 0.0


def max_drawdown(returns: Sequence[float]) -> float:
    """Largest peak-to-trough fall of the compounded return path."""
    cumulative = 1.0
    peak = 1.0
    drawdown = 0.0
    for value in returns:
        cumulative *= 1 + value
        if cumulative > peak:
            peak = cumulative
        current = (peak - cumulative) / peak
        if current > drawdown:
            drawdown = current
    return drawdown


def sharpe_ratio(
    returns: Sequence[float],
    risk_free: float = RISK_FREE_RATE,
    periods_per_year: float = TRADING_DAYS_PER_YEAR,
) -> Optional[float]:
    """(Annualised mean return - risk-free) / annualised volatility."""
    volatility = annualised_volatility(returns, periods_per_year)
    if volatility == 0:
        return None
    return (mean(returns) * periods_per_year - risk_free) / volatility


# -------------------------------------------------------------- valuation


def terminal_value_perpetuity(
    last_fcf: float, discount_rate: float, terminal_growth: float
) -> Optional[float]:
    """Gordon growth terminal value; ``None`` unless discount > growth."""
    if discount_rate <= terminal_growth:
        return None
    return last_fcf * (1 + terminal_growth) / (discount_rate - terminal_growth)


@dataclass(frozen=True)
class DcfYear:
    year: int
    free_cash_flow: float
    discount_factor: float
    present_value: float


@dataclass(frozen=True)
class DcfResult:
    years: Tuple[DcfYear, ...]
    pv_of_forecast: float
    terminal_value: float
    pv_of_terminal_value: float
    enterprise_value: float
    equity_value: float
    value_per_share: Optional[float]
    upside_percent: Optional[float]
    method: str
    terminal_share: Optional[float]


def dcf_value(
    base_fcf: float,
    growth: float,
    discount_rate: float,
    *,
    terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
    years: int = FORECAST_YEARS,
    shares: Optional[float] = None,
    net_debt: float = 0.0,
    exit_multiple: Optional[float] = None,
    current_price: Optional[float] = None,
) -> DcfResult:
    """Discount ``years`` of growing free cash flow plus a terminal value.

    Year ``t`` cash flow is ``base_fcf * (1 + growth) ** t``. The terminal
    value is a growing perpetuity on the final year, or ``exit_multiple``
    times final-year free cash flow when a multiple is given. Rates are
    fractions. ``method`` is ``"perpetuity"`` or ``"exit multiple"``.
    """
    if isinstance(years, bool) or not isinstance(years, int):
        raise ValueError("the forecast must be a whole number of years")
    if not 1 <= years <= MAX_DCF_YEARS:
        raise ValueError(f"the forecast must be 1 to {MAX_DCF_YEARS} years")
    if discount_rate <= -1 or growth <= -1:
        raise ValueError("rates must be above -100%")
    if shares is not None and shares <= 0:
        raise ValueError("shares outstanding must be above zero")
    if exit_multiple is not None and exit_multiple <= 0:
        raise ValueError("the exit multiple must be above zero")
    if current_price is not None and current_price <= 0:
        raise ValueError("the share price must be above zero")
    rows: List[DcfYear] = []
    pv_of_forecast = 0.0
    for year in range(1, years + 1):
        fcf = base_fcf * (1 + growth) ** year
        present = fcf / (1 + discount_rate) ** year
        rows.append(DcfYear(year, fcf, 1 / (1 + discount_rate) ** year, present))
        pv_of_forecast += present
    final_fcf = rows[-1].free_cash_flow
    if exit_multiple is None:
        terminal = terminal_value_perpetuity(final_fcf, discount_rate, terminal_growth)
        if terminal is None:
            raise ValueError(
                "the discount rate must be above the terminal growth rate, "
                "otherwise the perpetuity has no finite value"
            )
        method = "perpetuity"
    else:
        terminal = exit_multiple * final_fcf
        method = "exit multiple"
    pv_terminal = terminal / (1 + discount_rate) ** years
    enterprise = pv_of_forecast + pv_terminal
    equity = enterprise - net_debt
    per_share = equity / shares if shares is not None else None
    upside = None
    if per_share is not None and current_price is not None:
        upside = (per_share - current_price) / current_price * 100
    return DcfResult(
        years=tuple(rows),
        pv_of_forecast=pv_of_forecast,
        terminal_value=terminal,
        pv_of_terminal_value=pv_terminal,
        enterprise_value=enterprise,
        equity_value=equity,
        value_per_share=per_share,
        upside_percent=upside,
        method=method,
        terminal_share=pv_terminal / enterprise if enterprise > 0 else None,
    )


def capm_cost_of_equity(
    beta: float,
    risk_free: float = RISK_FREE_RATE,
    equity_risk_premium: float = EQUITY_RISK_PREMIUM,
) -> float:
    """CAPM: risk-free rate plus beta times the equity risk premium."""
    return risk_free + beta * equity_risk_premium


@dataclass(frozen=True)
class DripYear:
    year: int
    starting_value: float
    contributions: float
    dividend_income: float
    reinvested: float
    ending_value: float
    yield_on_cost: float


def simulate_drip(
    initial_investment: float,
    starting_yield: float,
    dividend_growth: float = 0.0,
    price_growth: float = 0.0,
    years: int = DEFAULT_DRIP_YEARS,
    *,
    annual_contribution: float = 0.0,
    reinvest: bool = True,
) -> List[DripYear]:
    """Year-by-year dividend reinvestment plan, as PW's ``simulateDrip``.

    The yield on the current value starts at ``starting_yield`` and grows by
    ``dividend_growth`` a year; the value grows by ``price_growth``, the
    reinvested dividends and ``annual_contribution`` (added at year end).
    Yield on cost is income over the initial investment plus contributions
    made in earlier years.
    """
    if isinstance(years, bool) or not isinstance(years, int):
        raise ValueError("years must be a whole number")
    if not 0 <= years <= MAX_DRIP_YEARS:
        raise ValueError(f"years must be 0 to {MAX_DRIP_YEARS}")
    rows: List[DripYear] = []
    value = initial_investment
    for year in range(1, years + 1):
        start = value
        yield_fraction = starting_yield * (1 + dividend_growth) ** (year - 1)
        income = start * yield_fraction
        reinvested = income if reinvest else 0.0
        appreciation = start * price_growth
        ending = start + appreciation + reinvested + annual_contribution
        cost_basis = initial_investment + annual_contribution * (year - 1)
        yield_on_cost = income / cost_basis if cost_basis > 0 else 0.0
        rows.append(
            DripYear(
                year=year,
                starting_value=start,
                contributions=annual_contribution,
                dividend_income=income,
                reinvested=reinvested,
                ending_value=ending,
                yield_on_cost=yield_on_cost,
            )
        )
        value = ending
    return rows


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


def _rate_after(text: str, keyword: str) -> Optional[float]:
    """A rate after ``keyword``; bare numbers count as percents (``rf 4``)."""
    match = re.search(keyword + _FILL + _RATE, text)
    return float(match.group("value").replace(",", "")) / 100 if match else None


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
    kind: str = "rate"  # "rate" (percent -> fraction), "amount" or "number"


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
    """A rate as typed, without trailing zeros: 0.025 -> '2.5%'."""
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


def _capm_inputs(found: Dict[str, float]) -> Tuple[float, float, float, List[str]]:
    """Beta, risk-free rate and equity risk premium, with notes on defaults."""
    beta = found["beta"]
    risk_free = found.get("risk_free", RISK_FREE_RATE)
    notes: List[str] = []
    if "premium" in found:
        premium = found["premium"]
    elif "market_return" in found:
        premium = found["market_return"] - risk_free
        notes.append(
            f"Equity risk premium {_rate_text(premium)} = market return "
            f"{_rate_text(found['market_return'])} minus the risk-free rate."
        )
    else:
        premium = EQUITY_RISK_PREMIUM
    defaults = []
    if "risk_free" not in found:
        defaults.append((f"risk-free rate ({_rate_text(RISK_FREE_RATE)})", '"risk-free 4%"'))
    if "premium" not in found and "market_return" not in found:
        defaults.append(
            (
                f"equity risk premium ({_rate_text(EQUITY_RISK_PREMIUM)})",
                '"equity risk premium 6%"',
            )
        )
    if len(defaults) == 2:
        notes.append(
            f"The {defaults[0][0]} and {defaults[1][0]} are Portfolio-Watcher's "
            f"defaults; say {defaults[0][1]} or {defaults[1][1]} to change them."
        )
    elif defaults:
        notes.append(
            f"The {defaults[0][0]} is Portfolio-Watcher's default; say "
            f"{defaults[0][1]} to change it."
        )
    return beta, risk_free, premium, notes


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
            f"Net debt = debt {cash(debt)} - cash {cash(held)} = {cash(debt - held)}."
        )
    return 0.0, "No net debt was given, so equity value equals enterprise value."


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
    currency = _currency(text)

    def cash(value: float) -> str:
        return _money(value, currency)

    typed_years = _years(text)
    years = FORECAST_YEARS if typed_years is None else typed_years
    growth = found.get("growth", 0.0)
    assumptions = [
        f"Free cash flow of {cash(base)} grows {_rate_text(growth)} a year for "
        f"{years} years"
        + (" (Portfolio-Watcher's default)" if typed_years is None else "")
        + "; each year is discounted from its end."
    ]
    if "growth" not in found:
        assumptions.append("No growth rate was given, so cash flow stays flat (0%).")
    if "discount" in found:
        discount = found["discount"]
        assumptions.append(f"Discount rate {_rate_text(discount)}, as given.")
        if "beta" in found:
            assumptions.append("The beta was ignored because a discount rate was given.")
    else:
        beta, risk_free, premium, notes = _capm_inputs(found)
        discount = capm_cost_of_equity(beta, risk_free, premium)
        assumptions.append(
            f"Discount rate {_percent(discount)} from CAPM: {_rate_text(risk_free)} + "
            f"{_trim(beta)} x {_rate_text(premium)}. Like Portfolio-Watcher, it uses "
            "the cost of equity alone and ignores debt."
        )
        assumptions.extend(notes)
    terminal = found.get("terminal")
    multiple = found.get("multiple")
    terminal_rate = DEFAULT_TERMINAL_GROWTH if terminal is None else terminal
    if multiple is not None:
        assumptions.append(
            f"Terminal value: {_trim(multiple)}x final-year free cash flow (exit multiple)."
        )
    elif discount <= terminal_rate:
        return _problem(
            f"I can't value that: the discount rate ({_rate_text(discount)}) must be "
            f"above terminal growth ({_rate_text(terminal_rate)}), or the terminal "
            "value never converges. Raise the discount rate, lower terminal growth "
            'or give an exit multiple such as "exit multiple 12x".'
        )
    else:
        assumptions.append(
            f"Terminal value: cash flow grows {_rate_text(terminal_rate)} a year forever "
            f"after year {years} (Gordon growth)"
            + (", Portfolio-Watcher's default rate." if terminal is None else ".")
        )
    net_debt, debt_note = _net_debt(found, cash)
    assumptions.append(debt_note)
    shares = found.get("shares")
    price = found.get("price")
    result = dcf_value(
        base,
        growth,
        discount,
        terminal_growth=terminal_rate,
        years=years,
        shares=shares,
        net_debt=net_debt,
        exit_multiple=multiple,
        current_price=price,
    )
    results = [
        f"Present value of {years} years of free cash flow: {cash(result.pv_of_forecast)}",
        f"Terminal value: {cash(result.terminal_value)}, worth "
        f"{cash(result.pv_of_terminal_value)} today",
        f"Enterprise value: {cash(result.enterprise_value)}",
        f"Equity value: {cash(result.equity_value)}",
    ]
    if result.value_per_share is not None and shares is not None:
        results.append(
            f"Value per share: {cash(result.value_per_share)} on {shares:,.0f} shares"
        )
        headline = f"DCF value: {cash(result.value_per_share)} a share"
    else:
        headline = f"DCF equity value: {cash(result.equity_value)}"
        assumptions.append('Add shares outstanding (e.g. "50m shares") for a value per share.')
    if result.upside_percent is not None and price is not None:
        side = "upside" if result.upside_percent >= 0 else "downside"
        results.append(
            f"Implied {side} against the {cash(price)} price: {result.upside_percent:+.1f}%"
        )
    if result.terminal_share is not None:
        share_line = (
            f"The terminal value is {_percent(result.terminal_share, 1)} of enterprise value"
        )
        if result.terminal_share > 0.7:
            share_line += (
                "; most of the value comes from beyond the forecast, so small changes "
                "to terminal growth or the discount rate move the result a lot"
            )
        results.append(share_line)
    if multiple is not None and terminal is not None and discount > terminal:
        other = dcf_value(
            base, growth, discount, terminal_growth=terminal, years=years,
            shares=shares, net_debt=net_debt,
        )
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
    beta, risk_free, premium, notes = _capm_inputs(found)
    cost = capm_cost_of_equity(beta, risk_free, premium)
    results = [
        f"{_rate_text(risk_free)} risk-free + {_trim(beta)} beta x "
        f"{_rate_text(premium)} equity risk premium = {_percent(cost)}"
    ]
    if beta < 0:
        results.append(
            "A negative beta means the stock tends to move against the market, so "
            "CAPM asks for less than the risk-free rate"
        )
    assumptions = notes + [
        "CAPM prices only market (beta) risk. Portfolio-Watcher uses it as the DCF "
        "discount rate, which ignores debt; a full WACC also weighs the after-tax "
        "cost of debt."
    ]
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
    return _reply(
        f"Fibonacci retracement levels between {_trim(low)} and {_trim(high)}:",
        [f"{label}: {_fixed(value)}" for label, value in fibonacci_levels(low, high)],
        (
            "Levels run from the high (0%) down to the low (100%), as "
            "Portfolio-Watcher draws them, so 38.2% marks a pullback of 38.2% of "
            "the move.",
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
    """A period written next to the indicator: "rsi(14)", "14-day rsi"."""
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


def _moving_average_report(text: str, values: List[float], only: bool, kind: str) -> _Report:
    label = kind.upper()
    period = _indicator_period(text, kind, only)
    notes: List[str] = []
    if period is None:
        period = MOVING_AVERAGE_PERIOD if len(values) >= MOVING_AVERAGE_PERIOD else len(values)
        notes.append(
            f"No {label} period was given, so it uses "
            + (f"{period}." if period == MOVING_AVERAGE_PERIOD else f"all {period} values.")
        )
    if len(values) < period:
        return [], [], f"{label}({period}) needs at least {period} values; you gave {len(values)}."
    series = (sma if kind == "sma" else ema)(values, period)
    latest = series[-1]
    last = values[-1]
    position = "above" if last > latest else "below" if last < latest else "level with"
    lines = [
        f"{label}({period}): {_plain(latest)}; the latest value {_plain(last)} is {position} it"
    ]
    defined = [value for value in series if value is not None]
    if 1 < len(defined) <= 10:
        lines.append(f"{label}({period}) series: " + ", ".join(_plain(v) for v in defined))
    if kind == "sma":
        notes.append(f"SMA({period}) is the plain average of the last {period} values.")
    else:
        notes.append(
            f"EMA({period}) starts from the first {period}-value average, then gives "
            f"each new value a weight of 2/({period}+1)."
        )
    return lines, notes, None


def _rsi_report(text: str, values: List[float], only: bool) -> _Report:
    period = _indicator_period(text, "rsi", only)
    notes: List[str] = []
    if period is None:
        period = RSI_PERIOD
        notes.append(f"No RSI period was given, so it uses the standard {RSI_PERIOD}.")
    if len(values) <= period:
        return [], [], f"RSI({period}) needs at least {period + 1} values; you gave {len(values)}."
    latest = rsi(values, period)[-1]
    if latest >= RSI_OVERBOUGHT:
        reading = f"{RSI_OVERBOUGHT} or above, which is often read as overbought"
    elif latest <= RSI_OVERSOLD:
        reading = f"{RSI_OVERSOLD} or below, which is often read as oversold"
    else:
        reading = f"between {RSI_OVERSOLD} and {RSI_OVERBOUGHT}, often read as neutral momentum"
    notes.append(
        f"RSI uses Wilder's smoothing over {period} periods, as in Portfolio-Watcher; "
        "overbought and oversold describe a tendency, not a forecast."
    )
    return [f"RSI({period}): {_fixed(latest)}, {reading}"], notes, None


def _macd_report(text: str, values: List[float], only: bool) -> _Report:
    settings = _MACD_SETTINGS.search(text)
    notes: List[str] = []
    if settings:
        fast, slow, signal = (int(settings.group(k)) for k in ("fast", "slow", "signal"))
        if fast >= slow:
            raise ValueError("the MACD fast period must be shorter than the slow period")
    else:
        fast, slow, signal = MACD_FAST, MACD_SLOW, MACD_SIGNAL
        notes.append("MACD uses the standard 12, 26 and 9 periods.")
    label = f"MACD({fast},{slow},{signal})"
    needed = slow + signal - 1
    if len(values) < slow:
        return [], [], (
            f"{label} needs at least {slow} values for the MACD line and {needed} for "
            f"the signal line; you gave {len(values)}."
        )
    result = macd(values, fast, slow, signal)
    line, signal_value, histogram = result.macd[-1], result.signal[-1], result.histogram[-1]
    if signal_value is None or histogram is None:
        text_line = (
            f"{label} line: {_plain(line)}; the signal line needs {needed} values and "
            f"you gave {len(values)}"
        )
    else:
        if line > signal_value:
            reading = "the line is above the signal, often read as positive momentum"
        elif line < signal_value:
            reading = "the line is below the signal, often read as negative momentum"
        else:
            reading = "the line equals the signal"
        text_line = (
            f"{label}: line {_plain(line)}, signal {_plain(signal_value)}, "
            f"histogram {_plain(histogram)}; {reading}"
        )
    notes.append(
        f"MACD is the {fast}-period EMA minus the {slow}-period EMA; the signal "
        f"line is a {signal}-period EMA of it."
    )
    return [text_line], notes, None


def _bollinger_report(text: str, values: List[float], only: bool) -> _Report:
    settings = _BOLLINGER_SETTINGS.search(text)
    period = int(settings.group("n")) if settings else _indicator_period(text, "bollinger", only)
    multiple = float(settings.group("k")) if settings and settings.group("k") else None
    if multiple is None:
        for pattern in _BOLLINGER_MULTIPLES:
            match = re.search(pattern, text)
            if match:
                multiple = float(match.group("k"))
                break
    defaults = []
    if period is None:
        period = BOLLINGER_PERIOD
        defaults.append(f"{BOLLINGER_PERIOD} periods")
    if multiple is None:
        multiple = BOLLINGER_MULTIPLE
        defaults.append(f"{_trim(BOLLINGER_MULTIPLE)} standard deviations")
    notes: List[str] = []
    if defaults:
        notes.append("Bollinger bands use the standard " + " and ".join(defaults) + ".")
    label = f"Bollinger({period}, {_trim(multiple)})"
    if len(values) < period:
        return [], [], f"{label} needs at least {period} values; you gave {len(values)}."
    bands = bollinger(values, period, multiple)
    upper, middle, lower = bands.upper[-1], bands.middle[-1], bands.lower[-1]
    last = values[-1]
    if last > upper:
        reading = "above the upper band, often read as stretched to the upside"
    elif last < lower:
        reading = "below the lower band, often read as stretched to the downside"
    else:
        reading = "inside the bands"
    notes.append(
        f"The bands are the {period}-period SMA plus or minus {_trim(multiple)} "
        "population standard deviations."
    )
    return [
        f"{label}: upper {_plain(upper)}, middle {_plain(middle)}, lower "
        f"{_plain(lower)}; the latest value {_plain(last)} is {reading}"
    ], notes, None


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
    lines: List[str] = []
    notes: List[str] = []
    missing: List[str] = []
    for kind in kinds:
        if kind in ("sma", "ema"):
            found, explained, short = _moving_average_report(text, values, only, kind)
        elif kind == "rsi":
            found, explained, short = _rsi_report(text, values, only)
        elif kind == "macd":
            found, explained, short = _macd_report(text, values, only)
        else:
            found, explained, short = _bollinger_report(text, values, only)
        if short:
            missing.append(short)
        lines.extend(found)
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
_RISK_FREE_WORDS = r"\b(?:risk[- ]?free(?:\s+rate)?|rf)\b"
_CONFIDENCE_PATTERNS = (
    r"(?P<value>\d+(?:\.\d+)?)\s*%\s*(?:confidence|level|var\b|value\s+at\s+risk|cvar"
    r"|es\b|expected\s+shortfall)",
    r"\bconfidence(?:\s+level)?\s*(?:of|=|:|at)?\s*(?P<value>\d+(?:\.\d+)?)\s*%?",
    r"\b(?:var|value\s+at\s+risk|expected\s+shortfall|cvar)\s+(?:at\s+)?"
    r"(?P<value>\d+(?:\.\d+)?)\s*%(?=\s*(?:\b(?:of|for|on)\b|:|$))",
)
_FREQUENCIES = (
    (r"\bdaily\b", 252, "daily"),
    (r"\bweekly\b", 52, "weekly"),
    (r"\bmonthly\b", 12, "monthly"),
    (r"\bquarterly\b", 4, "quarterly"),
    (
        r"\b(?:annual|yearly)\s+(?:returns?|prices?|closes?|data|values?|observations?)\b",
        1,
        "yearly",
    ),
)


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


def _periods_per_year(text: str) -> Tuple[int, str]:
    match = re.search(
        r"\b(?P<n>\d+)\s+(?:periods?|observations?|returns?)\s+(?:a|per)\s+year\b", text
    )
    if match and int(match.group("n")) > 0:
        return int(match.group("n")), "as given"
    for pattern, count, label in _FREQUENCIES:
        if re.search(pattern, text):
            return count, label
    return TRADING_DAYS_PER_YEAR, 'daily, the default; say "monthly" or "weekly" to change it'


def _confidence(text: str) -> float:
    for pattern in _CONFIDENCE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            value = float(match.group("value"))
            return value / 100 if value > 1 else value
    return DEFAULT_CONFIDENCE


def _drawdown_points(prices: Sequence[float]) -> Tuple[float, float]:
    peak = prices[0]
    worst = (0.0, prices[0], prices[0])
    for price in prices:
        peak = max(peak, price)
        if (peak - price) / peak > worst[0]:
            worst = ((peak - price) / peak, peak, price)
    return worst[1], worst[2]


_VOLATILITY_WORDS = r"(?:volatility|vol|standard\s+deviation|std\.?\s*dev\.?|stdev|sd|sigma)"
_RETURN_LABEL = r"(?:(?:annual(?:i[sz]ed)?|expected|average|mean|excess)\s+)*returns?"
_SUMMARY_FIELDS = (
    _Field(
        "return",
        (r"(?<!free )(?<!market )\b" + _RETURN_LABEL + r"\b" + _FILL + _RATE,),
        (_RATE + r"\s*" + _RETURN_LABEL + r"\b",),
    ),
    _Field(
        "volatility",
        (r"\b" + _VOLATILITY_WORDS + r"\b" + _FILL + _RATE,),
        (_RATE + r"\s*(?:annual(?:i[sz]ed)?\s+)?" + _VOLATILITY_WORDS + r"\b",),
    ),
)


def _summary_sharpe(text: str) -> Optional[str]:
    """A Sharpe ratio from a typed annual return and volatility, not a series."""
    typed_risk_free = re.search(_RISK_FREE_WORDS + _FILL + _RATE, text)
    taken = [typed_risk_free.span("value")] if typed_risk_free else []
    found = _read_fields(text, _SUMMARY_FIELDS, taken)
    if (
        "return" not in found
        or "volatility" not in found
        or len(re.findall(_NUM, text)) > 2 + len(taken)
    ):
        return None
    annual_return, volatility = found["return"], found["volatility"]
    if volatility <= 0:
        return _problem("Volatility must be above zero for a Sharpe ratio.")
    excess = bool(re.search(r"\bexcess\s+returns?\b", text))
    if excess:
        risk_free = 0.0
    elif typed_risk_free:
        risk_free = float(typed_risk_free.group("value").replace(",", "")) / 100
    else:
        risk_free = RISK_FREE_RATE
    ratio = (annual_return - risk_free) / volatility
    if excess:
        working = f"{_rate_text(annual_return)} / {_rate_text(volatility)} = {_fixed(ratio)}"
        rule = "The return is already in excess of the risk-free rate, so nothing is subtracted."
    else:
        working = (
            f"({_rate_text(annual_return)} - {_rate_text(risk_free)}) / "
            f"{_rate_text(volatility)} = {_fixed(ratio)}"
        )
        rule = "Sharpe ratio = (return - risk-free rate) / volatility"
        rule += "." if typed_risk_free else (
            f"; {_rate_text(RISK_FREE_RATE)} is Portfolio-Watcher's default rate."
        )
    headline = f"Sharpe ratio: {_fixed(ratio)}" + (
        "" if excess else f" (risk-free {_rate_text(risk_free)})"
    )
    assumptions = [
        "The return and volatility are annual figures, as typed; numbers without % "
        "are read as percents.",
        rule,
    ]
    return _reply(headline, [working], assumptions)


def _solve_risk(text: str) -> Optional[str]:
    intent = _RISK_INTENT.search(text)
    if not intent:
        return None
    if re.search(r"\bsharpe\b", text):
        summary = _summary_sharpe(text)
        if summary is not None:
            return summary
    raw, percent, left_out = _typed_series(text, (intent.end(), 0))
    if len(raw) < 2:
        return None
    metric = _risk_metric(intent.group(0))
    # Skewness, kurtosis and t describe the typed numbers themselves unless
    # they are called prices.
    sample = metric in ("skewness", "kurtosis", "t", "stats")
    says_prices = bool(_PRICE_WORDS.search(text))
    prices: Optional[List[float]] = None
    if percent:
        returns = [value / 100 for value in raw]
        reading = "Read the numbers as percent returns (1% = 0.01)."
    elif not says_prices and (sample or _RETURN_WORDS.search(text) or any(v < 0 for v in raw)):
        if any(abs(value) > 1 for value in raw):
            returns = [value / 100 for value in raw]
            reading = (
                "Read the numbers as percent returns because some are bigger than 1; "
                "write 0.01 for 1% to use decimals."
            )
        else:
            returns = list(raw)
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
        prices = raw
        returns = simple_returns(raw)
        reading = (
            f"Read the {len(raw)} numbers as prices, oldest first, giving "
            f'{len(returns)} simple returns; say "returns" if they already are.'
        )
    if len(returns) < 2:
        return _problem(
            f"I need at least 3 prices to measure risk; you gave {len(raw)}. If these are "
            'returns, say "returns" or add % signs.'
        )
    periods, frequency = _periods_per_year(text)
    confidence = _confidence(text)
    typed_risk_free = _rate_after(text, _RISK_FREE_WORDS)
    risk_free = RISK_FREE_RATE if typed_risk_free is None else typed_risk_free
    count = len(returns)
    average = mean(returns)
    volatility = annualised_volatility(returns, periods)
    var = historical_var(returns, confidence)
    shortfall = expected_shortfall(returns, confidence)
    drawdown = max_drawdown(returns)
    sharpe = sharpe_ratio(returns, risk_free, periods)
    t_stat = t_statistic(returns)
    level = _rate_text(confidence)

    drawdown_line = f"Max drawdown: {_percent(drawdown)}"
    if prices is not None and drawdown > 0:
        peak, trough = _drawdown_points(prices)
        drawdown_line += f" (from {_trim(peak)} down to {_trim(trough)})"
    elif prices is None:
        drawdown_line += " of the compounded returns"
    if sharpe is None:
        sharpe_line = "Sharpe ratio: not defined, because the returns do not vary"
    else:
        sharpe_line = f"Sharpe ratio: {_fixed(sharpe)} (risk-free {_rate_text(risk_free)})"
    t_text = "n/a" if t_stat is None else _fixed(t_stat)
    metrics = {
        "return": f"Annualised return: {_percent(average * periods)} (average x {periods})",
        "volatility": f"Annualised volatility: {_percent(volatility)}",
        "var": f"Historical {level} VaR: {_percent(var)} in one period",
        "es": f"Expected shortfall ({level}): {_percent(shortfall)} average loss in the tail",
        "drawdown": drawdown_line,
        "sharpe": sharpe_line,
    }
    headlines = {
        "skewness": f"Skewness: {_fixed(skewness(returns))}",
        "kurtosis": f"Excess kurtosis: {_fixed(kurtosis(returns))}",
        "t": f"t-statistic: {t_text}",
        "stats": f"Return statistics for {count} returns:",
    }
    headline = metrics.pop(metric) if metric in metrics else headlines[metric]
    results = list(metrics.values()) + [
        f"Per period: mean {_percent(average)}, median {_percent(median(returns))}, "
        f"standard deviation {_percent(std_dev(returns))}",
        f"Skewness {_fixed(skewness(returns))}, excess kurtosis {_fixed(kurtosis(returns))}, "
        f"t-statistic {t_text}",
    ]
    if count < MIN_SIGNIFICANT_OBSERVATIONS:
        results.append(
            f"With only {count} returns these figures are rough; Portfolio-Watcher "
            f"treats an average as significant only with {MIN_SIGNIFICANT_OBSERVATIONS}+ "
            f"observations and |t| above {SIGNIFICANCE_T}"
        )
    elif t_stat is not None and abs(t_stat) > SIGNIFICANCE_T:
        results.append(
            "The average return is statistically different from zero "
            f"(|t| above {SIGNIFICANCE_T})"
        )
    else:
        results.append(
            "The average return is not statistically different from zero "
            f"(|t| at most {SIGNIFICANCE_T})"
        )
    assumptions = [
        reading,
        f"{periods} periods a year ({frequency}): volatility scales with its square "
        "root and the average return with the count.",
        "VaR and expected shortfall are historical: they come from the sorted returns, "
        "with no distribution assumed.",
    ]
    if left_out:
        assumptions.insert(1, _left_out_note(left_out))
    if max(1, math.floor((1 - confidence) * count)) == 1 and var > 0:
        assumptions.append(
            f"With {count} returns the {level} tail is just the worst period, so VaR and "
            "expected shortfall both equal that loss."
        )
    sharpe_note = "Sharpe ratio = (annualised return - risk-free rate) / annualised volatility"
    if typed_risk_free is None:
        sharpe_note += f"; {_rate_text(RISK_FREE_RATE)} is Portfolio-Watcher's default rate"
    assumptions.append(sharpe_note + ".")
    assumptions.append(
        "Standard deviation is the sample estimate (n - 1); skewness and kurtosis use "
        "population moments, as in Portfolio-Watcher."
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
    typed_years = _years(text)
    years = DEFAULT_DRIP_YEARS if typed_years is None else typed_years
    if years < 1:
        return _problem("A DRIP projection needs at least 1 year.")
    starting_yield = found["yield"]
    dividend_growth = found.get("dividend_growth", 0.0)
    price_growth = found.get("price_growth", 0.0)
    reinvest = not _NO_REINVEST.search(text)
    currency = _currency(text)

    def cash(value: float) -> str:
        return _money(value, currency)

    def run(reinvesting: bool) -> List[DripYear]:
        return simulate_drip(
            initial, starting_yield, dividend_growth, price_growth, years,
            annual_contribution=contribution, reinvest=reinvesting,
        )

    rows = run(reinvest)
    other = run(not reinvest)
    final = rows[-1].ending_value
    dividends = _total([row.dividend_income for row in rows])
    shown = rows if years <= 10 else [
        row for row in rows if row.year == 1 or row.year % 5 == 0 or row.year == years
    ]
    results = [
        f"Year {row.year}: dividends {cash(row.dividend_income)}, value "
        f"{cash(row.ending_value)}, yield on cost {_percent(row.yield_on_cost)}"
        for row in shown
    ]
    total_line = f"Total dividends: {cash(dividends)}"
    if contribution:
        total_line += f"; contributions {cash(contribution * years)}"
    results.append(total_line)
    if reinvest:
        paid = _total([row.dividend_income for row in other])
        results.append(
            f"Taking dividends as cash instead: value {cash(other[-1].ending_value)} "
            f"plus {cash(paid)} paid out"
        )
    else:
        results.append(f"Reinvesting them instead would give {cash(other[-1].ending_value)}")
    if dividend_growth:
        final_yield = starting_yield * (1 + dividend_growth) ** (years - 1)
        yield_note = (
            f"The dividend yield on the current value starts at {_rate_text(starting_yield)} "
            f"and grows {_rate_text(dividend_growth)} a year, reaching "
            f"{_percent(final_yield)} in year {years}, as in Portfolio-Watcher's model."
        )
    else:
        yield_note = (
            f"The dividend yield on the current value stays at {_rate_text(starting_yield)}; "
            'add e.g. "5% dividend growth" to grow it.'
        )
    assumptions = [yield_note]
    if "price_growth" in found:
        assumptions.append(f"The share price grows {_rate_text(price_growth)} a year.")
    else:
        assumptions.append(
            'The share price stays flat; add e.g. "4% price growth" to change that.'
        )
    if monthly is not None:
        assumptions.append(
            f"{cash(monthly)} a month is added as {cash(contribution)} at each year end."
        )
    elif contribution:
        assumptions.append(f"{cash(contribution)} is added at each year end.")
    if typed_years is None:
        assumptions.append(f"{years} years, the default horizon.")
    assumptions.append(
        "Yield on cost is the year's dividends divided by the money put in before "
        "that year. Taxes, fees and share rounding are ignored."
    )
    start = cash(initial)
    if contribution:
        if monthly is not None:
            extra = f"{cash(monthly)} a month"
        else:
            extra = f"{cash(contribution)} a year"
        start = f"{start} plus {extra}" if initial else extra
    headline = (
        f"DRIP projection: {start} grows to {cash(final)} in {years} years "
        + ("with dividends reinvested" if reinvest else "with dividends paid out")
    )
    return _reply(headline, results, assumptions)


# ------------------------------------------------------------- entry points

_EXAMPLES = (
    "dcf with fcf 100m growth 8% discount 9% terminal 2.5% 50m shares net debt 200m",
    "cost of equity for beta 1.3",
    "rsi 5 of 44, 44.3, 44.1, 43.6, 44.5, 44.9, 45.2",
    "sma 5 of 10, 11, 12, 13, 14, 15",
    "bollinger(5, 2) of 10 11 12 11 13 14",
    "fibonacci levels between 100 and 150",
    "max drawdown of 100, 120, 90, 130",
    "sharpe ratio of monthly returns 1%, 2%, -1%, 3%",
    "drip 10000 at 3% yield 5% dividend growth for 10 years",
)


def solve(text: str) -> Optional[str]:
    """Answer an investment-maths request, or ``None`` if ``text`` isn't one.

    Handles DCF, CAPM, Fibonacci levels, technicals (SMA, EMA, RSI, MACD,
    Bollinger), risk and return statistics, and DRIP projections, using only
    the numbers in ``text``. ``None`` also means the needed numbers are missing.
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
    """How to ask, with examples that work offline."""
    lines = ["I can do investment maths on numbers you type (no market data). Try:"]
    lines.extend(f"- {example}" for example in _EXAMPLES)
    lines.extend((DISCLAIMER, CREDIT))
    return "\n".join(lines)
