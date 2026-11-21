"""Paper trading with OpenTrading's demo stocks: simulated orders only.

OpenTrading (https://charles2ke.github.io/OpenTrading/, source at
https://github.com/charles2ke/OpenTrading) is the user's own paper-trading app.
Jarvis keeps no copy of it. The demo stocks and indices with their prices, the
starting cash, stock search, order checks and fills, and portfolio valuation
all come from the app's ``src/core/trading.js``, and the saved portfolio is
read and written with its ``src/core/storage.js``; ``bridges/opentrading.mjs``
runs both from the ``projects/OpenTrading`` submodule with Node.js. Prices are
always the app's built-in demo values: Jarvis never asks for live quotes.

:func:`handle` understands plain-English requests ("paper buy 10 AAPL",
"simulate selling 5 Tesla", "show my paper portfolio", "paper quote MSFT",
ISIN, CUSIP and SEDOL lookups, "paper indices", "reset my paper portfolio")
and words OpenTrading's answer; a rejected order quotes the app's own reason.
The portfolio is OpenTrading's own portfolio object, kept in Jarvis memory
under ``PORTFOLIO_KEY``. Text that isn't a paper-trading request returns
``None``, in most cases without needing the project.

Nothing here can place a real order. Jarvis has no brokerage connection, and
every reply says the trade is simulated; a buy or sell that doesn't say paper,
simulated, demo or similar is refused and the paper command shown instead.

When the project or Node.js is missing, :func:`handle` raises
:class:`jarvis.projects.ProjectUnavailable` with setup steps, except that a
request to trade real shares is still refused, with the steps added.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from jarvis import projects
from jarvis.nl import words_to_number

__all__ = [
    "CREDIT",
    "Instrument",
    "Market",
    "MarketIndex",
    "PORTFOLIO_KEY",
    "PROJECT",
    "REPO_URL",
    "SAFETY_LINE",
    "SITE_URL",
    "handle",
    "market",
    "resolve_instrument",
    "symbols",
    "usage",
]

PROJECT = "OpenTrading"
SITE_URL = projects.PROJECTS[PROJECT].site
REPO_URL = projects.PROJECTS[PROJECT].repo
CREDIT = f"From {PROJECT}: {SITE_URL}"
SAFETY_LINE = "Simulated trading with demo prices — no real money or orders."
PRICE_NOTE = (
    "Prices are OpenTrading's built-in demo values, not live quotes, and are shown in "
    "US dollars as in the app."
)

PORTFOLIO_KEY = "paper_portfolio"

_INDEX_NOTE = "Index levels are OpenTrading's built-in demo values, not live."
_FRESH_NOTE = (
    "(The paper portfolio saved in memory wasn't one OpenTrading accepts, so a fresh one "
    "was used.)"
)
_REFUSAL = (
    "I can't place real trades: Jarvis has no brokerage connection and never moves "
    "real money."
)

Quantity = Union[int, float]


@dataclass(frozen=True)
class Instrument:
    """A demo stock as OpenTrading lists it."""

    symbol: str
    ticker: str
    isin: str
    cusip: str
    sedol: str
    name: str
    exchange: str
    country: str
    price: float
    previous_close: float


@dataclass(frozen=True)
class MarketIndex:
    """A demo market index; ``change`` is in percent."""

    name: str
    code: str
    flag: str
    value: float
    change: float


@dataclass(frozen=True)
class Market:
    """OpenTrading's starting cash, demo stocks and demo indices."""

    starting_cash: float
    instruments: Tuple[Instrument, ...]
    indices: Tuple[MarketIndex, ...]


@dataclass(frozen=True)
class _Holding:
    instrument: Instrument
    quantity: float
    average_price: float
    value: float
    return_value: float


@dataclass(frozen=True)
class _Summary:
    """OpenTrading's valuation of a portfolio."""

    cash: float
    holdings: Tuple[_Holding, ...]
    total: float
    today: float


@dataclass(frozen=True)
class _Order:
    """OpenTrading's answer to one order; ``most`` is only set when it was rejected."""

    error: str
    quantity: float
    held: float
    cash_before: float
    most: int
    summary: _Summary
    fresh: bool


# ------------------------------------------------------------ project data

def _field(data: Any, key: str) -> Any:
    return data.get(key) if isinstance(data, dict) else None


def _finite(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _real(data: Any, key: str) -> float:
    value = _field(data, key)
    if not _finite(value):
        raise projects.ProjectError(f"OpenTrading gave no usable {key!r}")
    return value


def _text(data: Any, key: str, required: bool = True) -> str:
    value = _field(data, key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        raise projects.ProjectError(f"OpenTrading gave no usable {key!r}")
    return value.strip()


def _list(data: Any, key: str) -> List[Any]:
    value = _field(data, key)
    if not isinstance(value, list):
        raise projects.ProjectError(f"OpenTrading gave no {key!r} list")
    return value


def _instrument(data: Any) -> Instrument:
    item = Instrument(
        _text(data, "symbol"),
        _text(data, "ticker", required=False),
        _text(data, "isin", required=False),
        _text(data, "cusip", required=False),
        _text(data, "sedol", required=False),
        _text(data, "name"),
        _text(data, "exchange", required=False),
        _text(data, "country", required=False),
        _real(data, "price"),
        _real(data, "previousClose"),
    )
    if item.price <= 0:
        raise projects.ProjectError(f"OpenTrading gave {item.symbol} no usable price")
    return item


def _index(data: Any) -> MarketIndex:
    return MarketIndex(
        _text(data, "name"),
        _text(data, "code"),
        _text(data, "flag", required=False),
        _real(data, "value"),
        _real(data, "change"),
    )


def _summary(data: Any) -> _Summary:
    return _Summary(
        _real(data, "cash"),
        tuple(
            _Holding(
                _instrument(row),
                _real(row, "quantity"),
                _real(row, "averagePrice"),
                _real(row, "value"),
                _real(row, "returnValue"),
            )
            for row in _list(data, "positions")
        ),
        _real(data, "portfolioValue"),
        _real(data, "dailyChange"),
    )


@lru_cache(maxsize=1)
def market() -> Market:
    """OpenTrading's starting cash, demo stocks and indices (read once per process)."""

    data = projects.call(PROJECT, "market")
    instruments = tuple(_instrument(item) for item in _list(data, "instruments"))
    if not instruments:
        raise projects.ProjectError("OpenTrading listed no stocks")
    return Market(
        _real(data, "startingCash"),
        instruments,
        tuple(_index(item) for item in _list(data, "indices")),
    )


def symbols() -> Tuple[str, ...]:
    """The stocks OpenTrading lets you paper trade, each as "SYMBOL (Name)"."""

    return tuple(f"{item.symbol} ({item.name})" for item in market().instruments)


@lru_cache(maxsize=64)
def _search(query: str) -> Tuple[Tuple[Instrument, ...], Tuple[MarketIndex, ...]]:
    """The demo stocks and indices OpenTrading's own search finds for ``query``."""

    data = projects.call(PROJECT, "search", {"query": query})
    return (
        tuple(_instrument(item) for item in _list(data, "instruments")),
        tuple(_index(item) for item in _list(data, "indices")),
    )


def _saved(memory: Any) -> Tuple[Any, bool]:
    """The portfolio saved in memory, and whether it had to be left out."""

    value = memory.get(PORTFOLIO_KEY)
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        return None, True
    return value, False


def _with_portfolio(memory: Any, action: str, **payload: Any) -> Tuple[Any, bool]:
    """Run ``action`` on the saved portfolio; also says if a fresh one was used."""

    saved, dropped = _saved(memory)
    data = projects.call(PROJECT, action, {"portfolio": saved, **payload})
    return data, dropped or _field(data, "discarded") is True


def _keep(memory: Any, data: Any) -> None:
    portfolio = _field(data, "portfolio")
    if not isinstance(portfolio, dict):
        raise projects.ProjectError("OpenTrading gave no portfolio to save")
    memory.set(PORTFOLIO_KEY, portfolio)


def _place(memory: Any, symbol: str, side: str, quantity: Union[Quantity, str]) -> _Order:
    """Send one order to OpenTrading; the portfolio is saved when it fills."""

    order = {"symbol": symbol, "side": side, "quantity": quantity}
    data, fresh = _with_portfolio(memory, "order", order=order)
    error = _field(data, "error")
    most = _field(data, "most")
    if not isinstance(error, str):
        raise projects.ProjectError("OpenTrading gave no order result")
    if error and (isinstance(most, bool) or not isinstance(most, int) or most < 0):
        raise projects.ProjectError("OpenTrading gave no usable 'most'")
    result = _Order(
        error,
        _real(data, "quantity"),
        _real(data, "held"),
        _real(data, "cashBefore"),
        most if error else 0,
        _summary(_field(data, "summary")),
        fresh,
    )
    if not error:
        _keep(memory, data)
    return result


# ------------------------------------------------------------------ stocks

_COMPANY_WORDS = re.compile(
    r"the|inc|incorporated|corp|corporation|co|company|plc|ag|se|ltd|limited"
    r"|holdings?|group|motors?|stocks?|shares?"
)


def _compact(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _company_key(text: str) -> str:
    """A company name in any case, without "'s" or words like "Inc" or "Holdings"."""

    words = re.findall(r"\w+", re.sub(r"['\u2019]s\b", "", text.casefold()))
    return " ".join(word for word in words if not _COMPANY_WORDS.fullmatch(word))


def resolve_instrument(query: str, fuzzy: bool = True) -> Optional[Instrument]:
    """The one OpenTrading demo stock ``query`` names, or ``None``.

    Exact matches come first: the symbol or ticker, an ISIN, CUSIP or SEDOL,
    or the company's name, ignoring words such as "Inc" or "Holdings". With
    ``fuzzy``, OpenTrading's own search also counts when it finds exactly one
    stock.
    """

    compact = _compact(query or "")
    name = _company_key(query or "")
    if not compact and not name:
        return None
    for item in market().instruments:
        codes = (item.symbol, item.ticker, item.isin, item.cusip, item.sedol)
        if compact and any(_compact(code) == compact for code in codes):
            return item
        if name and name == _company_key(item.name):
            return item
    if fuzzy:
        found = _search(query)[0]
        if len(found) == 1:
            return found[0]
    return None


# -------------------------------------------------------------- formatting

def _usd(value: float) -> str:
    """``value`` in dollars and cents, such as "$1,234.50" or "-$3.00"."""

    digits = f"{abs(value):,.2f}"
    sign = "-" if value < 0 and digits != "0.00" else ""
    return f"{sign}${digits}"


def _signed_usd(value: float) -> str:
    text = _usd(value)
    return text if text.startswith("-") else f"+{text}"


def _number(value: Quantity) -> str:
    """A share count as it was given, with thousands separators ("1,000", "2.5")."""

    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value:,}"


def _shares(quantity: Quantity) -> str:
    return f"{_number(quantity)} share{'' if quantity == 1 else 's'}"


def _join(*parts: str) -> str:
    return ", ".join(part for part in parts if part)


def _instrument_line(item: Instrument) -> str:
    where = _join(item.exchange, item.country)
    return (
        f"{item.symbol} {item.name}{f' ({where})' if where else ''}: {_usd(item.price)}, "
        f"previous close {_usd(item.previous_close)}"
    )


def _index_line(index: MarketIndex) -> str:
    return f"{index.name} ({index.code}): {index.value:,.2f} ({index.change:+.2f}%)"


def _finish(lines: Sequence[str]) -> str:
    return "\n".join([*lines, SAFETY_LINE, CREDIT])


def _fresh(used: bool) -> List[str]:
    return [_FRESH_NOTE] if used else []


def _demo_list() -> str:
    return "OpenTrading's demo stocks are " + ", ".join(symbols()) + "."


# ----------------------------------------------------------------- replies

def _holding(summary: _Summary, symbol: str) -> Optional[_Holding]:
    return next((row for row in summary.holdings if row.instrument.symbol == symbol), None)


def _fill_reply(side: str, item: Instrument, order: _Order) -> str:
    bought = side == "buy"
    cash = order.summary.cash
    lines = [
        f"Paper order filled: {'bought' if bought else 'sold'} {_shares(order.quantity)} of "
        f"{item.symbol} ({item.name}) at the demo price of {_usd(item.price)}.",
        f"- {'Cost' if bought else 'Proceeds'}: {_usd(abs(order.cash_before - cash))}",
        f"- {'Cash left' if bought else 'Cash now'}: {_usd(cash)}",
    ]
    holding = _holding(order.summary, item.symbol)
    if holding is None:
        lines.append(f"- You no longer hold any {item.symbol}")
    else:
        lines.append(
            f"- You now hold {_shares(holding.quantity)} of {item.symbol} at an average "
            f"{_usd(holding.average_price)}"
        )
    return _finish([*lines, PRICE_NOTE, *_fresh(order.fresh)])


def _rejected_reply(side: str, item: Instrument, order: _Order) -> str:
    lines = [f"Paper order not placed: {order.error}"]
    # Only for a whole number of shares above what OpenTrading would take now.
    if isinstance(order.quantity, int) and order.quantity > order.most:
        if side == "buy":
            lines.append(
                f"- {item.symbol}'s demo price is {_usd(item.price)} a share, and you have "
                f"{_usd(order.cash_before)} in paper cash"
            )
        elif order.held:
            lines.append(f"- You hold {_shares(order.held)} of {item.symbol}")
        else:
            lines.append(
                f"- You hold no {item.symbol}; buy some first, e.g. paper buy 10 {item.symbol}"
            )
        if order.most:
            lines.append(
                f"- You can {side} up to {_shares(order.most)} right now: "
                f"paper {side} {order.most} {item.symbol}"
            )
    return _finish([*lines, *_fresh(order.fresh)])


def _portfolio_reply(memory: Any) -> str:
    data, fresh = _with_portfolio(memory, "portfolio")
    summary = _summary(_field(data, "summary"))
    if not summary.holdings:
        return _finish([
            f"Your paper portfolio holds {_usd(summary.cash)} in cash and no positions.",
            "- Try: paper buy 10 AAPL",
            *_fresh(fresh),
        ])
    count = len(summary.holdings)
    lines = [f"Your paper portfolio ({count} position{'' if count == 1 else 's'}):"]
    for row in summary.holdings:
        item = row.instrument
        lines.append(
            f"- {item.symbol} ({_join(item.name, item.exchange)}): {_shares(row.quantity)} at "
            f"an average {_usd(row.average_price)}; demo price {_usd(item.price)}, value "
            f"{_usd(row.value)}, unrealised P/L {_signed_usd(row.return_value)}"
        )
    lines.extend((
        f"- Cash: {_usd(summary.cash)}",
        f"- Total value: {_usd(summary.total)}",
        f"- Today: {_signed_usd(summary.today)} versus the previous close",
        PRICE_NOTE,
        *_fresh(fresh),
    ))
    return _finish(lines)


def _quote_reply(item: Instrument) -> str:
    lines = [
        f"{item.symbol} ({_join(item.name, item.exchange, item.country)}): demo price "
        f"{_usd(item.price)}, previous close {_usd(item.previous_close)}.",
    ]
    codes = _join(*(
        f"{label} {code}"
        for label, code in (("ISIN", item.isin), ("CUSIP", item.cusip), ("SEDOL", item.sedol))
        if code
    ))
    if codes:
        lines.append(f"- {codes}")
    return _finish([*lines, PRICE_NOTE])


def _list_reply(headline: str, instruments: Sequence[Instrument],
                indices: Sequence[MarketIndex] = ()) -> str:
    lines = [headline]
    lines.extend(f"- {_instrument_line(item)}" for item in instruments)
    lines.extend(f"- {_index_line(index)}" for index in indices)
    if instruments:
        lines.append(PRICE_NOTE)
    if indices:
        lines.append(_INDEX_NOTE)
    return _finish(lines)


def _lookup_reply(query: str, label: str = "") -> str:
    instruments, indices = _search(query)
    if label:
        indices = ()
    shown = f"{label} {query}".strip()
    if not instruments and not indices:
        kind = "stock" if label else "stock or index"
        return _finish([f'No OpenTrading demo {kind} matches "{shown}".', _demo_list()])
    if len(instruments) == 1 and not indices:
        return _quote_reply(instruments[0])
    total = len(instruments) + len(indices)
    return _list_reply(
        f'{total} demo match{"" if total == 1 else "es"} for "{shown}":', instruments, indices
    )


def _reset_reply(memory: Any) -> str:
    data, _ = _with_portfolio(memory, "reset")
    cleared = _field(data, "cleared")
    if isinstance(cleared, bool) or not isinstance(cleared, int) or cleared < 0:
        raise projects.ProjectError("OpenTrading gave no usable 'cleared'")
    summary = _summary(_field(data, "summary"))
    _keep(memory, data)
    holdings = "" if summary.holdings else " and no positions"
    done = f" Cleared {cleared} position{'' if cleared == 1 else 's'}." if cleared else ""
    return _finish([
        f"Your paper portfolio is reset to {_usd(summary.cash)} in cash{holdings}.{done}"
    ])


def _real_trade_reply(command: str, known: bool) -> str:
    lines = [_REFUSAL]
    if known:
        lines.append(f"- To practise with demo money instead, say: {command}")
    else:
        lines.append(
            "- To practise with demo money instead, use one of OpenTrading's demo stocks, "
            f"e.g. {command}"
        )
        lines.append(f"- {_demo_list()}")
    return _finish(lines)


def _refusing(build: Callable[[], Optional[str]], share_words: bool) -> Optional[str]:
    """``build()``; a request to trade shares is refused even without OpenTrading."""

    if not share_words:
        return build()
    try:
        return build()
    except projects.ProjectUnavailable as exc:
        return _finish([
            _REFUSAL,
            f"- To practise with demo money instead, Jarvis needs {PROJECT}. {exc}",
        ])


def _example_quantity(quantity: Any) -> int:
    return quantity if isinstance(quantity, int) and quantity >= 1 else 10


def _unknown_stock_reply(side: str, query: str, quantity: Any) -> str:
    example = f"paper {side} {_example_quantity(quantity)} AAPL"
    if query:
        return _finish([
            f'"{query}" is not one of OpenTrading\'s demo stocks.',
            _demo_list(),
            f"- For example: {example}",
        ])
    return _finish([f"Which demo stock? For example: {example}.", _demo_list()])


# -------------------------------------------------------------- understanding

_PAPER_WORD = r"(?:paper|demo|virtual|mock|practi[cs]e)"
_TRADING_WORD = (
    r"(?:trad(?:e|es|ed|ing|er)|buy(?:s|ing)?|sell(?:s|ing)?|bought|sold|purchas\w*"
    r"|orders?|portfolios?|accounts?|cash|positions?|holdings?|balance|quotes?|prices?"
    r"|stocks|shares?|ind(?:ex|ices|exes)|markets?|watchlist|look\s*up|lookup|search\w*"
    r"|find|help)"
)
_PAPER = re.compile(
    rf"\b{_PAPER_WORD}[- ]?{_TRADING_WORD}\b|\bon\s+paper\b(?!\s+\w)"
    r"|\b(?:simulat\w*|pretend\w*)\b|\bopentrading\b",
    re.IGNORECASE,
)
_TRADING_TALK = re.compile(
    rf"\b{_PAPER_WORD}[- ]?{_TRADING_WORD}\b|\bopentrading\b"
    r"|\b(?:simulat\w*|pretend\w*)\s+(?:(?:to|a|an)\s+)?(?:trad\w*|buy\w*|sell\w*|portfolio)",
    re.IGNORECASE,
)
_SIDE = re.compile(
    r"\b(?:(?P<buy>buy(?:s|ing)?|bought|purchas(?:e|es|ed|ing))|(?P<sell>sell(?:s|ing)?|sold))\b",
    re.IGNORECASE,
)
_NOT_A_REQUEST = re.compile(r"(?:bought|sold|purchased|buys|sells|purchases)$", re.IGNORECASE)
_HELP = re.compile(
    r"\bhelp\b|\bcommands?\b|\busage\b|\bhow\s+(?:do|can)\s+(?:i|you|we)\b"
    r"(?!.*\b(?:portfolios?|positions?|holdings?|cash|balance)\b)",
    re.IGNORECASE,
)
_RESET = re.compile(
    r"\b(?:reset|clear|restart|wipe|erase)\b(?=(?:\s+\w+){0,3}?\s+(?:portfolios?|accounts?"
    r"|positions?|holdings?|cash|balance|paper|trad\w*|orders?|simulat\w*|everything|all|it)\b"
    r"|\W*$)|\bstart\s+(?:over|again|afresh|fresh|from\s+scratch)\b",
    re.IGNORECASE,
)
_NEGATED = re.compile(r"\b(?:don['\u2019]?t|do\s+not|never|not)\s+(?:\w+\s+){0,2}$", re.I)
_QUESTION = re.compile(r"^(?:how|what|why|when|which|does|is|are|should)\b", re.IGNORECASE)
_IDENTIFIER = re.compile(
    r"\b(?P<kind>isin|cusip|sedol)(?:\s+(?:code|number))?\s*(?:[:#=]\s*|\bis\s+)?"
    r"(?P<code>(?=[A-Za-z0-9-]*\d)[A-Za-z0-9][A-Za-z0-9-]{4,})\b",
    re.IGNORECASE,
)
_IDENTIFIER_OF = re.compile(
    r"\b(?P<kind>isin|cusip|sedol)s?(?:\s+(?:code|number))?\s+(?:of|for)\s+(?P<query>[^?!;]+)",
    re.IGNORECASE,
)
_SEARCH = re.compile(r"\b(?:look\s*up|lookup|search(?:\s+for)?|find)\b", re.IGNORECASE)
_INDICES = re.compile(r"\bind(?:ex|ices|exes)\b", re.IGNORECASE)
_QUOTE = re.compile(
    r"\b(?:quotes?|prices?|watchlist|stocks|instruments|markets?|symbols|tickers)\b",
    re.IGNORECASE,
)
_PORTFOLIO = re.compile(
    r"\b(?:portfolios?|positions?|holdings?|balance|accounts?|cash|money|p\s*&\s*l|pnl"
    r"|performance|net\s+worth)\b",
    re.IGNORECASE,
)
_SHARE_WORDS = re.compile(r"\b(?:shares?|stocks?)\b", re.IGNORECASE)
_AMOUNT = r"\d[\d,]*(?:\.\d+)?"
_DOLLAR_ORDER = re.compile(
    rf"^\s*(?:me\s+)?(?:(?:us\$|\$|usd)\s*(?P<amount>{_AMOUNT})(?:\s*(?:dollars|usd|bucks))?"
    rf"|(?P<spelled>{_AMOUNT})\s*(?:dollars|usd|bucks)\b)(?:\s+worth)?",
    re.IGNORECASE,
)
_ALL_SHARES = re.compile(
    r"^\s*(?:(?:all|every|each)(?:\s+(?:of\s+)?(?:my|the|our))?(?:\s+(?:shares?|stocks?))?"
    r"(?:\s+(?:of|in))?|everything(?:\s+(?:in|of))?|(?:my|the|our)\s+(?:entire|whole|full)"
    r"(?:\s+(?:position|holding|stake)s?)?(?:\s+(?:of|in))?)(?=\s|$)",
    re.IGNORECASE,
)
_LEADING_WORDS = re.compile(r"\s*((?:[A-Za-z]+(?:-[A-Za-z]+)*\s*){1,5})")
_QUANTITY_DIGITS = re.compile(
    r"\s*(?P<qty>[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|[+-]?\.\d+)"
    r"(?:\s*[x\u00d7](?=\s|$))?(?![\w.])"
)
_BEFORE_QUANTITY = re.compile(
    r"^\s*(?:(?:me|my|of|another|more|further|an?\s+(?:extra|additional|further))\s+)*",
    re.IGNORECASE,
)
_BEFORE_NAME = re.compile(
    r"^\s*(?:(?:x|more|extra|additional)\s+)*(?:(?:shares?|stocks?|units?)\s+)?"
    r"(?:(?:of|in)\s+)?(?:the\s+)?",
    re.IGNORECASE,
)
_NAME_STOP = re.compile(
    r"\s+(?:at|for|with|using|in|on|from|to|into|via|please|now|today|and|then|so|because"
    r"|if|limit|stop|market|order|worth)\b|\s*@|[,;:!?()&]|\.(?:\s|$)",
    re.IGNORECASE,
)
_AFTER_NAME = re.compile(
    r"(?:(?:^|\s+)(?:shares?|stocks?|units?|positions?|holdings?|stake))+\s*$", re.IGNORECASE
)
_TRAILING_QUANTITY = re.compile(
    r"\s*(?P<name>[^\d,$]+?)\s*(?:[,x\u00d7]\s*)?(?P<qty>\d{1,3}(?:,\d{3})+|\d+)"
    r"\s*(?:shares?|stocks?|units?)?\s*[.!]?\s*$",
    re.IGNORECASE,
)
_PRICE_LIMIT = re.compile(
    r"\b(?:at|for)\s+(?:a\s+)?(?:(?:limit|stop)\s+(?:price\s+)?(?:of\s+)?)?(?:us\$|\$|usd)?"
    r"\s*\d[\d,]*(?:\.\d+)?(?!\d|[,.]\d)"
    r"(?!\s*(?:%|percent|days?|weeks?|months?|years?|hours?|hrs?|minutes?|mins?|am|pm|:\d))"
    r"|@\s*(?:us\$|\$)?\s*\d|\b(?:limit|stop)(?:[- ]loss)?\s+(?:orders?|prices?|at|@|\$|\d)",
    re.IGNORECASE,
)
_QUERY_FILLER = re.compile(
    r"^\s*(?:(?:of|for|on|in|from|about|the|a|an|me|my|all|any|stock|stocks|share|shares"
    r"|ticker|tickers|symbol|symbols|company|companies|code|index|indices|indexes|quotes?"
    r"|prices?|data|info|information|details|listed|called|named)\s+)*",
    re.IGNORECASE,
)
_QUERY_END = re.compile(
    r"[?!;]|(?:^|\s+)(?:please|now|today|can|could|do|does|did|are|is|am|was|were|will"
    r"|would|should|i|you|we|they|available|there|have|has|that|which)\b"
    r"|(?:^|\s+)(?:in|on|with|using|via|from)\s+(?:my\s+|the\s+)?(?:opentrading|paper|demo|virtual"
    r"|mock|practi[cs]e|simulat\w*)\b",
    re.IGNORECASE,
)


def _count(digits: str) -> Optional[Quantity]:
    """``digits`` as a number of shares, or ``None`` when it is too large to use."""

    number = Decimal(digits.replace(",", ""))
    value = float(number)
    if not math.isfinite(value):
        return None
    return int(number) if number == number.to_integral_value() else value


def _leading_quantity(text: str) -> Tuple[Optional[Quantity], str]:
    """A share count at the start of ``text`` ("10", "1,000", "ten", "a hundred")."""
    text = _BEFORE_QUANTITY.sub("", text, count=1)
    match = _QUANTITY_DIGITS.match(text)
    if match:
        return _count(match.group("qty")), text[match.end():]
    words = _LEADING_WORDS.match(text)
    if not words:
        return None, text
    tokens = list(re.finditer(r"[A-Za-z]+(?:-[A-Za-z]+)*", words.group(1)))
    for count in range(len(tokens), 0, -1):
        end = words.start(1) + tokens[count - 1].end()
        phrase = text[words.start(1):end].lower()
        if phrase in ("a", "an"):
            value: Optional[Quantity] = 1
        elif phrase.startswith(("a ", "an ")):
            value = words_to_number("one " + phrase.split(" ", 1)[1])
        else:
            value = words_to_number(phrase)
        if value is not None:
            return value, text[end:]
    return None, text


def _starts_with_count(text: str) -> bool:
    text = _BEFORE_QUANTITY.sub("", text, count=1)
    if _QUANTITY_DIGITS.match(text) or _DOLLAR_ORDER.match(text):
        return True
    first = re.match(r"\s*([A-Za-z]+)", text)
    return bool(first) and first.group(1).lower() not in ("a", "an") and (
        words_to_number(first.group(1)) is not None
    )


def _multiple_orders(text: str, side: re.Match[str]) -> bool:
    later_sides = _SIDE.finditer(text, side.end())
    if any(_starts_with_count(text[later.end():]) for later in later_sides):
        return True
    return bool(re.search(
        r"(?:,\s+|\s+(?:and|plus)\s+|\s*&\s*)(?:\d|\$)", text[side.end():], re.IGNORECASE
    ))


def _instrument_query(text: str) -> str:
    rest = _BEFORE_NAME.sub("", text, count=1)
    rest = _NAME_STOP.split(rest, maxsplit=1)[0]
    return _AFTER_NAME.sub("", rest).strip(" .'\"")


def _query_after(text: str, end: int) -> str:
    rest = _QUERY_FILLER.sub("", text[end:] + " ", count=1)
    return _QUERY_END.split(rest, maxsplit=1)[0].strip(" .:,'\"")


def _mentioned_instruments(text: str) -> List[Instrument]:
    """Demo stocks named outright in ``text`` by symbol, identifier or name."""
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9-]*", text)
    found: Dict[str, Instrument] = {}
    for size in (2, 1):
        for start in range(len(words) - size + 1):
            item = resolve_instrument(" ".join(words[start:start + size]), fuzzy=False)
            if item is not None:
                found.setdefault(item.symbol, item)
    return [item for item in market().instruments if item.symbol in found]


def _command(side: str, quantity: Any, symbol: str) -> str:
    amount = "all my" if quantity is None else _number(quantity)
    return f"paper {side} {amount} {symbol}"


def _dollar_order(side: str, amount: float, query: str, paper: bool,
                  share_words: bool) -> Optional[str]:
    item = resolve_instrument(query, fuzzy=paper) if query else None
    if item is None:
        if paper:
            return _unknown_stock_reply(side, query, None)
        return _real_trade_reply(f"paper {side} 10 AAPL", False) if share_words else None
    whole = int(Decimal(repr(amount)) / Decimal(repr(item.price)))
    command = f"paper {side} {max(whole, 1)} {item.symbol}"
    if not paper:
        return _real_trade_reply(command, True)
    if whole < 1:
        headline = (
            f"{_usd(amount)} is less than one share of {item.symbol} at the demo price of "
            f"{_usd(item.price)}, and OpenTrading orders are for a number of shares."
        )
    else:
        headline = (
            "OpenTrading orders are for a number of shares, not an amount of money: "
            f"{_usd(amount)} is {_shares(whole)} of {item.symbol} at the demo price of "
            f"{_usd(item.price)}, rounded down."
        )
    return _finish([headline, f"- Say: {command}", PRICE_NOTE])


def _find_stock(after: str, quantity: Optional[Quantity], rest: str,
                trailing: Optional[re.Match[str]], paper: bool
                ) -> Tuple[Optional[Instrument], Optional[Quantity], str, str]:
    """The stock an order names, with its quantity, the name asked for and what follows."""
    query = _instrument_query(rest)
    if trailing is not None:
        name = _instrument_query(trailing.group("name"))
        if name and resolve_instrument(name, fuzzy=paper):
            quantity = _count(trailing.group("qty"))
            query, rest = name, ""
    item = resolve_instrument(query, fuzzy=paper) if query else None
    if item is None:
        code = _IDENTIFIER.search(after)
        item = resolve_instrument(code.group("code"), fuzzy=False) if code else None
    if item is None and not query and isinstance(quantity, int):
        item = resolve_instrument(str(quantity), fuzzy=False)
        if item is not None:
            quantity = None
    return item, quantity, query, rest


def _order(text: str, side_match: re.Match[str], memory: Any, paper: bool) -> Optional[str]:
    """Run, explain or refuse the order in ``text``; ``None`` if there isn't one."""
    side = "buy" if side_match.group("buy") else "sell"
    if not paper and _NOT_A_REQUEST.match(side_match.group(0)):
        return None
    share_words = bool(_SHARE_WORDS.search(text))
    after = text[side_match.end():]
    dollars = _DOLLAR_ORDER.match(after)
    if dollars:
        amount = float((dollars.group("amount") or dollars.group("spelled")).replace(",", ""))
        if not math.isfinite(amount):
            return None
        query = _instrument_query(after[dollars.end():])
        if paper:
            return _dollar_order(side, amount, query, True, share_words)
        return _refusing(lambda: _dollar_order(side, amount, query, False, share_words),
                         share_words)
    everything = _ALL_SHARES.match(after)
    quantity: Optional[Quantity]
    if everything:
        quantity, rest = None, after[everything.end():]
    else:
        quantity, rest = _leading_quantity(after)
    sell_all = bool(everything) and side == "sell"
    trailing = _TRAILING_QUANTITY.match(after) if quantity is None and not everything else None
    if not paper:
        if quantity is None and not sell_all and trailing is None:
            return None

        def refuse() -> Optional[str]:
            item, amount, _, _ = _find_stock(after, quantity, rest, trailing, False)
            if (amount is None and not sell_all) or (item is None and not share_words):
                return None
            if item is None:
                example = _command(side, None if sell_all else _example_quantity(amount), "AAPL")
                return _real_trade_reply(example, False)
            return _real_trade_reply(_command(side, amount, item.symbol), True)

        return _refusing(refuse, share_words)
    item, quantity, query, rest = _find_stock(after, quantity, rest, trailing, True)
    if _QUESTION.match(text):
        if item is not None and (quantity is not None or sell_all):
            return _finish([
                f"To place that paper order, say: {_command(side, quantity, item.symbol)}",
                "- Paper orders fill straight away at the demo price; nothing real is bought "
                "or sold.",
            ])
        return usage()
    if quantity is None and item is None and not everything:
        return None
    if _multiple_orders(text, side_match):
        return _finish(["One paper order at a time, please: for example, paper buy 10 AAPL."])
    if item is None:
        return _unknown_stock_reply(side, query, quantity)
    if quantity is None and not sell_all:
        return _finish([
            f"How many shares of {item.symbol}? For example: paper {side} 10 {item.symbol}.",
        ])
    if _PRICE_LIMIT.search(rest):
        return _finish([
            "OpenTrading has no limit or stop orders: paper orders fill straight away at the "
            f"demo price ({item.symbol}: {_usd(item.price)}).",
            f"- To {side} at that price, say: {_command(side, quantity, item.symbol)}",
            PRICE_NOTE,
        ])
    order = _place(memory, item.symbol, side, "all" if sell_all else quantity)
    if sell_all and not order.held:
        return _finish([
            f"Paper order not placed: you hold no {item.symbol} to sell.",
            f"- Buy some first, e.g. paper buy 10 {item.symbol}",
            *_fresh(order.fresh),
        ])
    if order.error:
        return _rejected_reply(side, item, order)
    return _fill_reply(side, item, order)


def _identifier_lookup(text: str) -> Optional[str]:
    code = _IDENTIFIER.search(text)
    if code:
        return _lookup_reply(code.group("code"), code.group("kind").upper())
    named = _IDENTIFIER_OF.search(text)
    if named:
        query = _query_after(named.group("query"), 0)
        item = resolve_instrument(query)
        if item is not None:
            return _quote_reply(item)
        return _finish([f'No OpenTrading demo stock matches "{query}".', _demo_list()])
    return None


def _market_reply(message: str, memory: Any) -> Optional[str]:
    """Lookups, indices, quotes and the portfolio, once paper context is clear."""
    portfolio_words = _PORTFOLIO.search(message)
    search = _SEARCH.search(message)
    indices = _INDICES.search(message)
    quote = _QUOTE.search(message)
    if not (search or indices or quote):
        return _portfolio_reply(memory) if portfolio_words else None
    if portfolio_words and not _mentioned_instruments(message):
        return _portfolio_reply(memory)
    if search:
        query = _query_after(message, search.end())
        if query:
            return _lookup_reply(query)
        everything = market()
        return _list_reply(
            "OpenTrading's demo stocks and indices:", everything.instruments, everything.indices
        )
    if indices:
        query = _query_after(message, indices.end())
        found = _search(query)[1] if query else market().indices
        if not found:
            return _finish([
                f'No demo index matches "{query}". The demo indices are '
                + ", ".join(f"{index.name} ({index.code})" for index in market().indices) + ".",
            ])
        return _list_reply("Demo market indices from OpenTrading:", (), found)
    query = _query_after(message, quote.end())
    item = resolve_instrument(query) if query else None
    if item is not None:
        return _quote_reply(item)
    named = _mentioned_instruments(message)
    if len(named) == 1:
        return _quote_reply(named[0])
    if named:
        return _list_reply("Demo quotes from OpenTrading:", named)
    if query:
        return _lookup_reply(query)
    return _list_reply("OpenTrading's demo stocks:", market().instruments)


def handle(text: str, memory: Any) -> Optional[str]:
    """Answer a paper-trading request, or ``None`` if ``text`` isn't one.

    Understands simulated orders ("paper buy 10 AAPL", "simulate selling 5
    Tesla"), the portfolio, resets, demo quotes, ISIN/CUSIP/SEDOL lookups,
    demo indices and help. A buy or sell of shares that doesn't say paper,
    simulated, demo or similar is never executed: the reply explains that
    Jarvis places no real trades and shows the paper command instead. Orders
    phrased as questions ("how do I paper buy 10 AAPL?") are explained, not
    placed. ``memory`` needs ``get`` and ``set``; the portfolio is kept under
    ``PORTFOLIO_KEY``.
    """
    message = " ".join((text or "").split())
    if not message:
        return None
    paper = bool(_PAPER.search(message))
    side = _SIDE.search(message)
    if paper:
        reset = _RESET.search(message)
        if reset and not _NEGATED.search(message[:reset.start()]):
            if side:
                return _finish([
                    "One thing at a time: say \"reset my paper portfolio\" to start again with "
                    f"{_usd(market().starting_cash)}, or give the order on its own, e.g. "
                    "paper buy 10 AAPL.",
                ])
            if _QUESTION.match(message):
                return _finish([
                    f"To start again with {_usd(market().starting_cash)} of paper cash and no "
                    "positions, say: reset my paper portfolio",
                ])
            return _reset_reply(memory)
        if _HELP.search(message) and not side:
            return usage()
        if side:
            reply = _order(message, side, memory, True)
            if reply is not None:
                return reply
    lookup = _identifier_lookup(message)
    if lookup is not None:
        return lookup
    if not paper:
        return _order(message, side, memory, False) if side else None
    reply = _market_reply(message, memory)
    if reply is not None:
        return reply
    return usage() if _TRADING_TALK.search(message) else None


def usage() -> str:
    """How to paper trade, with examples; needs neither the project nor Node.js."""
    return _finish([
        "Paper trading with OpenTrading's demo stocks: practise with pretend cash. Try:",
        "- paper buy 10 AAPL",
        "- paper sell 5 shares of Apple",
        "- simulate buying 3 Microsoft",
        "- show my paper portfolio",
        "- paper quote AAPL",
        "- look up the ISIN of Apple",
        "- demo stocks",
        "- paper indices",
        "- reset my paper portfolio",
        "Orders fill straight away at the demo price when OpenTrading accepts them.",
    ])
