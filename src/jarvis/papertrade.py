"""Paper trading with OpenTrading's demo stocks: simulated orders only.

Ported from OpenTrading by charles2ke
(https://github.com/charles2ke/OpenTrading) at commit
a252eb47adae72cab77b04368f682b74710e9968, Apache License 2.0:

* ``src/core/trading.js``: the demo ``instruments`` and ``indices``,
  ``STARTING_CASH``, ``searchInstruments``, ``searchIndices``,
  ``createPortfolio``, ``getInstrument``, ``validateOrder``,
  ``executeOrder``, ``summarizePortfolio`` and ``isPortfolio``.
* ``src/core/storage.js``: ``loadPortfolio`` and ``savePortfolio``.
* ``src/app.js``: money shown in US dollars and the "Bought 10 AAPL" wording.

Modified for Jarvis (the change notice Apache-2.0 section 4(b) asks for):
rewritten in Python; the portfolio lives in Jarvis memory under
``PORTFOLIO_KEY`` instead of browser storage; live quotes (Finnhub or Twelve
Data through OpenTrading's server) and every server API are left out, so
prices are always the built-in demo snapshot; booleans are not accepted as
share counts; and :func:`handle` adds a plain-text command parser.

Nothing here can place a real order. Jarvis has no brokerage connection, and
every reply says the trade is simulated.
"""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from jarvis.nl import words_to_number

__all__ = [
    "CREDIT",
    "INDICES",
    "INSTRUMENTS",
    "Instrument",
    "MAX_ORDER_SHARES",
    "MarketIndex",
    "PORTFOLIO_KEY",
    "PROJECT",
    "PortfolioSummary",
    "PositionSummary",
    "REPO_URL",
    "SAFETY_LINE",
    "SITE_URL",
    "STARTING_CASH",
    "SYMBOLS",
    "create_portfolio",
    "execute_order",
    "get_instrument",
    "handle",
    "is_portfolio",
    "load_portfolio",
    "resolve_instrument",
    "save_portfolio",
    "search_indices",
    "search_instruments",
    "summarize_portfolio",
    "usage",
    "validate_order",
]

PROJECT = "OpenTrading"
SITE_URL = "https://charles2ke.github.io/OpenTrading/"
REPO_URL = "https://github.com/charles2ke/OpenTrading"
SOURCE_COMMIT = "a252eb47adae72cab77b04368f682b74710e9968"
CREDIT = f"From {PROJECT}: {SITE_URL}"
SAFETY_LINE = "Simulated trading with demo prices — no real money or orders."
PRICE_NOTE = (
    "Prices are demo values from OpenTrading's built-in snapshot, not live quotes; "
    "OpenTrading shows them all in US dollars."
)

PORTFOLIO_KEY = "paper_portfolio"
STARTING_CASH = 100_000
MAX_ORDER_SHARES = 10_000
_MAX_SAFE_INTEGER = 2**53 - 1

UNSUPPORTED_STOCK = "Select a supported stock."
BAD_QUANTITY = "Shares must be a whole number between 1 and 10,000."
BAD_SIDE = "Choose buy or sell."
NOT_ENOUGH_CASH = "This order exceeds your available cash."
NOT_ENOUGH_SHARES = "You cannot sell more shares than you own."

Portfolio = Dict[str, Any]


@dataclass(frozen=True)
class Instrument:
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
    name: str
    code: str
    flag: str
    value: float
    change: float


INSTRUMENTS: Tuple[Instrument, ...] = (
    Instrument("AAPL", "AAPL", "US0378331005", "037833100", "2046251", "Apple",
               "NASDAQ", "US", 232.14, 228.76),
    Instrument("MSFT", "MSFT", "US5949181045", "594918104", "2588173", "Microsoft",
               "NASDAQ", "US", 418.79, 420.43),
    Instrument("TSLA", "TSLA", "US88160R1014", "88160R101", "B616C79", "Tesla",
               "NASDAQ", "US", 351.62, 342.11),
    Instrument("7203", "7203", "JP3633400001", "892331307", "6900643", "Toyota Motor",
               "TSE", "JP", 18.42, 18.19),
    Instrument("SAP", "SAP", "DE0007164600", "803054204", "4846288", "SAP",
               "XETRA", "DE", 271.24, 267.8),
    Instrument("HSBA", "HSBA", "GB0005405286", "404280406", "0540528", "HSBC",
               "LSE", "GB", 13.76, 13.59),
)

INDICES: Tuple[MarketIndex, ...] = (
    MarketIndex("S&P 500", "SPX", "\U0001F1FA\U0001F1F8", 6481.4, 0.72),
    MarketIndex("FTSE 100", "UKX", "\U0001F1EC\U0001F1E7", 9312.05, 0.31),
    MarketIndex("Nikkei 225", "NKY", "\U0001F1EF\U0001F1F5", 42520.27, -0.46),
    MarketIndex("DAX", "DAX", "\U0001F1E9\U0001F1EA", 24309.62, 0.58),
)

SYMBOLS: Tuple[str, ...] = tuple(f"{item.symbol} ({item.name})" for item in INSTRUMENTS)


# ------------------------------------------------------------------- search

def _search_text(value: str) -> str:
    return re.sub(r"[^a-z0-9&]+", " ", value.lower()).strip()


def _term_groups(query: Optional[str]) -> List[List[str]]:
    text = "" if query is None else str(query)
    groups = [_search_text(group).split() for group in text.split(",")]
    return [terms for terms in groups if terms]


def _matches(fields: Sequence[str], groups: Sequence[Sequence[str]]) -> bool:
    haystack = _search_text(" ".join(fields))
    return any(all(term in haystack for term in terms) for terms in groups)


def search_instruments(query: Optional[str]) -> List[Instrument]:
    """Demo stocks matching ``query``, as OpenTrading's ``searchInstruments``.

    Symbol, ticker, ISIN, CUSIP, SEDOL, name, exchange and country are
    searched, ignoring case and punctuation. Every word must appear; commas
    separate alternatives ("tsla, msft"). An empty query returns them all.
    """
    groups = _term_groups(query)
    if not groups:
        return list(INSTRUMENTS)
    return [
        item for item in INSTRUMENTS
        if _matches(
            (item.symbol, item.ticker, item.isin, item.cusip, item.sedol, item.name,
             item.exchange, item.country),
            groups,
        )
    ]


def search_indices(query: Optional[str]) -> List[MarketIndex]:
    """Demo indices whose name or code matches ``query`` (``searchIndices``)."""
    groups = _term_groups(query)
    if not groups:
        return list(INDICES)
    return [index for index in INDICES if _matches((index.name, index.code), groups)]


def get_instrument(symbol: Any) -> Optional[Instrument]:
    """The demo stock with exactly this symbol, or ``None``."""
    return next((item for item in INSTRUMENTS if item.symbol == symbol), None)


_COMPANY_WORDS = re.compile(
    r"\b(?:the|inc|incorporated|corp|corporation|co|company|plc|ag|se|ltd|limited"
    r"|holdings?|group|motors?|stocks?|shares?)\b"
)


def _company_key(text: str) -> str:
    return " ".join(_COMPANY_WORDS.sub(" ", _search_text(text.replace("'s", ""))).split())


def resolve_instrument(query: str, fuzzy: bool = True) -> Optional[Instrument]:
    """The one demo stock ``query`` names, or ``None``.

    Exact matches come first: symbol or ticker ("aapl"), ISIN, CUSIP or SEDOL
    ("US0378331005") and company name ("Tesla", "Toyota", "HSBC Holdings").
    With ``fuzzy`` a :func:`search_instruments` query that matches exactly one
    stock also counts ("apple nasdaq").
    """
    key = _search_text(query or "")
    if not key:
        return None
    compact = re.sub(r"[^A-Z0-9]", "", query.upper())
    name = _company_key(query)
    for item in INSTRUMENTS:
        if compact in (item.symbol, item.ticker, item.isin, item.cusip, item.sedol):
            return item
        if name and name == _company_key(item.name):
            return item
    if fuzzy:
        found = search_instruments(query)
        if len(found) == 1:
            return found[0]
    return None


# ---------------------------------------------------------------- portfolio

def create_portfolio() -> Portfolio:
    """A fresh paper portfolio: 100,000 in cash and no positions."""
    return {"cash": STARTING_CASH, "positions": {}}


def _finite(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _safe_integer(value: Any) -> bool:
    return _finite(value) and float(value).is_integer() and abs(value) <= _MAX_SAFE_INTEGER


def _share_count(value: Any) -> Optional[Union[int, float]]:
    """JavaScript's ``Number(value)`` for an order quantity; ``None`` is NaN.

    Numbers pass through and numeric strings are read ("2", " 2 ", "1e3",
    "0x10"); an empty string is 0. Booleans and ``None`` are rejected,
    which JavaScript would read as 1 and 0.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return 0
    if re.fullmatch(r"0[xX][0-9a-fA-F]+|0[oO][0-7]+|0[bB][01]+", text):
        return int(text, 0)
    if re.fullmatch(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?", text):
        return float(text)
    return None


def _held(portfolio: Mapping[str, Any], symbol: str) -> Any:
    position = portfolio["positions"].get(symbol)
    held = position.get("quantity") if isinstance(position, Mapping) else None
    return 0 if held is None else held


def validate_order(portfolio: Mapping[str, Any], order: Mapping[str, Any]) -> str:
    """The first problem with ``order``, or ``""`` when it can be filled.

    ``order`` has ``symbol``, ``side`` ("buy" or "sell") and ``quantity``;
    the messages and their order are OpenTrading's ``validateOrder``.
    """
    instrument = get_instrument(order.get("symbol"))
    quantity = _share_count(order.get("quantity"))
    if instrument is None:
        return UNSUPPORTED_STOCK
    if quantity is None or not _safe_integer(quantity) or not 1 <= quantity <= MAX_ORDER_SHARES:
        return BAD_QUANTITY
    side = order.get("side")
    if side not in ("buy", "sell"):
        return BAD_SIDE
    if side == "buy" and instrument.price * quantity > portfolio["cash"]:
        return NOT_ENOUGH_CASH
    if side == "sell" and quantity > _held(portfolio, instrument.symbol):
        return NOT_ENOUGH_SHARES
    return ""


def execute_order(
    portfolio: Portfolio, order: Mapping[str, Any]
) -> Tuple[Portfolio, str]:
    """Fill ``order`` at the demo price: ``(new_portfolio, "")``.

    An invalid order returns ``(portfolio, error)`` with the same object. A
    buy recomputes the average price, a sell keeps it, and a position that
    reaches zero shares is removed. The input portfolio is never changed.
    """
    error = validate_order(portfolio, order)
    if error:
        return portfolio, error
    quantity = int(_share_count(order["quantity"]))
    instrument = get_instrument(order["symbol"])
    existing = portfolio["positions"].get(instrument.symbol)
    if existing is None:
        existing = {"quantity": 0, "averagePrice": 0}
    direction = 1 if order["side"] == "buy" else -1
    next_quantity = existing["quantity"] + direction * quantity
    positions = dict(portfolio["positions"])
    if next_quantity == 0:
        positions.pop(instrument.symbol, None)
    else:
        if order["side"] == "buy":
            average = (
                existing["averagePrice"] * existing["quantity"] + instrument.price * quantity
            ) / next_quantity
        else:
            average = existing["averagePrice"]
        positions[instrument.symbol] = {"quantity": next_quantity, "averagePrice": average}
    cash = portfolio["cash"] - direction * instrument.price * quantity
    return {"cash": cash, "positions": positions}, ""


@dataclass(frozen=True)
class PositionSummary:
    symbol: str
    name: str
    exchange: str
    country: str
    quantity: float
    average_price: float
    price: float
    previous_close: float
    value: float
    return_value: float


@dataclass(frozen=True)
class PortfolioSummary:
    cash: float
    positions: Tuple[PositionSummary, ...]
    portfolio_value: float
    daily_change: float


def summarize_portfolio(portfolio: Mapping[str, Any]) -> PortfolioSummary:
    """Value each position at the demo price, as ``summarizePortfolio``.

    ``return_value`` is the unrealised gain against the average price and
    ``daily_change`` the move since the previous close.
    """
    rows: List[PositionSummary] = []
    for symbol, position in portfolio["positions"].items():
        item = get_instrument(symbol)
        quantity = position["quantity"]
        rows.append(
            PositionSummary(
                symbol=item.symbol,
                name=item.name,
                exchange=item.exchange,
                country=item.country,
                quantity=quantity,
                average_price=position["averagePrice"],
                price=item.price,
                previous_close=item.previous_close,
                value=item.price * quantity,
                return_value=(item.price - position["averagePrice"]) * quantity,
            )
        )
    holdings = 0.0
    daily = 0.0
    for row in rows:
        holdings += row.value
        daily += (row.price - row.previous_close) * row.quantity
    return PortfolioSummary(
        cash=portfolio["cash"],
        positions=tuple(rows),
        portfolio_value=portfolio["cash"] + holdings,
        daily_change=daily,
    )


def is_portfolio(value: Any) -> bool:
    """Whether ``value`` is a well-formed portfolio (``isPortfolio``).

    Cash must be a finite number of at least 0, and ``positions`` a mapping
    of demo symbols to a whole ``quantity`` above 0 and an ``averagePrice``
    above 0. Booleans and numeric strings do not count as numbers.
    """
    if not isinstance(value, dict) or not _finite(value.get("cash")) or value["cash"] < 0:
        return False
    positions = value.get("positions")
    if not isinstance(positions, dict):
        return False
    for symbol, position in positions.items():
        if get_instrument(symbol) is None or not isinstance(position, dict):
            return False
        quantity = position.get("quantity")
        average = position.get("averagePrice")
        if not _safe_integer(quantity) or quantity <= 0:
            return False
        if not _finite(average) or average <= 0:
            return False
    return True


def load_portfolio(memory: Any) -> Portfolio:
    """The saved paper portfolio, or a fresh one if none is saved or it is invalid."""
    value = memory.get(PORTFOLIO_KEY)
    return copy.deepcopy(value) if is_portfolio(value) else create_portfolio()


def save_portfolio(memory: Any, portfolio: Portfolio) -> None:
    """Store ``portfolio`` in memory as JSON-safe data under ``PORTFOLIO_KEY``."""
    if not is_portfolio(portfolio):
        raise TypeError("Refusing to store an invalid portfolio.")
    memory.set(PORTFOLIO_KEY, copy.deepcopy(portfolio))


# --------------------------------------------------------------- formatting

def _usd(value: float) -> str:
    """Dollars like OpenTrading's ``Intl.NumberFormat("en-US", USD)``."""
    digits = f"{abs(value):,.2f}"
    sign = "-" if value < 0 and digits != "0.00" else ""
    return f"{sign}${digits}"


def _signed_usd(value: float) -> str:
    text = _usd(value)
    return text if text.startswith("-") else f"+{text}"


def _number(value: float) -> str:
    """At most two decimals, like ``Intl.NumberFormat`` in OpenTrading."""
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _shares(quantity: float) -> str:
    return f"{_number(quantity)} share{'' if quantity == 1 else 's'}"


def _change_text(item: Instrument) -> str:
    change = (item.price - item.previous_close) / item.previous_close * 100
    return f"{'+' if change >= 0 else ''}{change:.2f}%"


def _index_change(index: MarketIndex) -> str:
    text = repr(float(index.change))
    text = text[:-2] if text.endswith(".0") else text
    return f"{'+' if index.change >= 0 else ''}{text}%"


def _instrument_line(item: Instrument) -> str:
    return (
        f"{item.symbol} {item.name} ({item.exchange}, {item.country}): {_usd(item.price)}, "
        f"{_change_text(item)} on the previous close"
    )


def _index_line(index: MarketIndex) -> str:
    return f"{index.name} ({index.code}): {_number(index.value)}, {_index_change(index)}"


def _finish(lines: Sequence[str]) -> str:
    return "\n".join([*lines, SAFETY_LINE, CREDIT])


def _demo_list() -> str:
    return "OpenTrading's demo stocks are " + ", ".join(SYMBOLS) + "."


# ------------------------------------------------------------------ replies

def _fill_reply(side: str, quantity: int, item: Instrument, portfolio: Portfolio) -> str:
    amount = item.price * quantity
    verb = "Bought" if side == "buy" else "Sold"
    # OpenTrading's "Bought 4 7203" reads as one number, so spell out numeric symbols.
    what = f"{_shares(quantity)} of " if item.symbol[:1].isdigit() else f"{_number(quantity)} "
    lines = [
        f"{verb} {what}{item.symbol} ({item.name}) at the demo price of "
        f"{_usd(item.price)} (paper trade).",
        f"- {'Cost' if side == 'buy' else 'Proceeds'}: {_usd(amount)}",
        f"- {'Cash left' if side == 'buy' else 'Cash now'}: {_usd(portfolio['cash'])}",
    ]
    position = portfolio["positions"].get(item.symbol)
    if position:
        lines.append(
            f"- You now hold {_shares(position['quantity'])} of {item.symbol} at an "
            f"average {_usd(position['averagePrice'])}"
        )
    else:
        lines.append(f"- You no longer hold any {item.symbol}")
    lines.append(PRICE_NOTE)
    return _finish(lines)


def _rejected_reply(error: str, side: str, quantity: Any, item: Instrument,
                    portfolio: Portfolio) -> str:
    lines = [f"Paper order not placed: {error}"]
    if error == NOT_ENOUGH_CASH:
        lines.append(
            f"- {_shares(quantity)} of {item.symbol} at {_usd(item.price)} would cost "
            f"{_usd(item.price * quantity)}; you have {_usd(portfolio['cash'])} in paper cash"
        )
        affordable = min(MAX_ORDER_SHARES, math.floor(portfolio["cash"] / item.price))
        if affordable >= 1:
            lines.append(
                f"- You can afford up to {_shares(affordable)}: "
                f"paper buy {affordable} {item.symbol}"
            )
    elif error == BAD_QUANTITY and _finite(quantity) and quantity > MAX_ORDER_SHARES:
        lines.append(f"- One order can be at most {MAX_ORDER_SHARES:,} shares; split it up")
    elif error == NOT_ENOUGH_SHARES:
        held = _held(portfolio, item.symbol)
        lines.append(
            f"- You hold {_shares(held)} of {item.symbol}" if held
            else f"- You hold no {item.symbol}; buy some first, e.g. paper buy 10 {item.symbol}"
        )
    return _finish(lines)


def _portfolio_reply(portfolio: Portfolio) -> str:
    summary = summarize_portfolio(portfolio)
    if not summary.positions:
        return _finish([
            f"Your paper portfolio holds {_usd(summary.cash)} in cash and no positions.",
            "- Try: paper buy 10 AAPL",
        ])
    count = len(summary.positions)
    lines = [f"Your paper portfolio ({count} position{'' if count == 1 else 's'}):"]
    for row in summary.positions:
        lines.append(
            f"- {row.symbol} ({row.name}, {row.exchange}): {_shares(row.quantity)} at an "
            f"average {_usd(row.average_price)}; demo price {_usd(row.price)}, value "
            f"{_usd(row.value)}, unrealised P/L {_signed_usd(row.return_value)}"
        )
    lines.extend((
        f"- Cash: {_usd(summary.cash)}",
        f"- Total value: {_usd(summary.portfolio_value)}",
        f"- Today: {_signed_usd(summary.daily_change)} versus the previous close",
        PRICE_NOTE,
    ))
    return _finish(lines)


def _quote_reply(item: Instrument) -> str:
    return _finish([
        f"{item.symbol} ({item.name}, {item.exchange}, {item.country}): demo price "
        f"{_usd(item.price)}, {_change_text(item)} on the previous close of "
        f"{_usd(item.previous_close)}.",
        f"- ISIN {item.isin}, CUSIP {item.cusip}, SEDOL {item.sedol}",
        PRICE_NOTE,
    ])


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
    instruments = search_instruments(query)
    indices = [] if label else search_indices(query)
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
    previous = load_portfolio(memory)
    save_portfolio(memory, create_portfolio())
    count = len(previous["positions"])
    cleared = f" Cleared {count} position{'' if count == 1 else 's'}." if count else ""
    return _finish([
        f"Your paper portfolio is reset to {_usd(STARTING_CASH)} in cash and no positions."
        + cleared
    ])


def _real_trade_reply(command: str, known: bool) -> str:
    lines = [
        "I can't place real trades: Jarvis has no brokerage connection and never moves "
        "real money.",
    ]
    if known:
        lines.append(f"- To practise with demo money instead, say: {command}")
    else:
        lines.append(
            "- To practise with demo money instead, use one of OpenTrading's demo stocks, "
            f"e.g. {command}"
        )
        lines.append(f"- {_demo_list()}")
    return _finish(lines)


def _example_quantity(quantity: Any) -> int:
    if isinstance(quantity, int) and 1 <= quantity <= MAX_ORDER_SHARES:
        return quantity
    return 10


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

_INDEX_NOTE = "Index levels are demo values from OpenTrading's built-in snapshot, not live."
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


def _leading_quantity(text: str) -> Tuple[Optional[Union[int, float]], str]:
    """A share count at the start of ``text`` ("10", "1,000", "ten", "a hundred")."""
    text = _BEFORE_QUANTITY.sub("", text, count=1)
    match = _QUANTITY_DIGITS.match(text)
    if match:
        number = float(match.group("qty").replace(",", ""))
        return (int(number) if number.is_integer() else number), text[match.end():]
    words = _LEADING_WORDS.match(text)
    if not words:
        return None, text
    tokens = list(re.finditer(r"[A-Za-z]+(?:-[A-Za-z]+)*", words.group(1)))
    for count in range(len(tokens), 0, -1):
        end = words.start(1) + tokens[count - 1].end()
        phrase = text[words.start(1):end].lower()
        if phrase in ("a", "an"):
            value: Optional[Union[int, float]] = 1
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
    return [item for item in INSTRUMENTS if item.symbol in found]


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
    whole = math.floor(amount / item.price)
    command = f"paper {side} {min(max(whole, 1), MAX_ORDER_SHARES)} {item.symbol}"
    if not paper:
        return _real_trade_reply(command, True)
    if whole < 1:
        headline = (
            f"{_usd(amount)} is less than one share of {item.symbol} at the demo price of "
            f"{_usd(item.price)}; OpenTrading orders are whole shares."
        )
    else:
        headline = (
            f"OpenTrading orders are whole shares: at the demo price of {_usd(item.price)}, "
            f"{_usd(amount)} is {_shares(whole)} of {item.symbol} ({_usd(whole * item.price)})."
        )
    lines = [headline, f"- Say: {command}"]
    if whole > MAX_ORDER_SHARES:
        lines.append(f"- One order can be at most {MAX_ORDER_SHARES:,} shares")
    lines.append(PRICE_NOTE)
    return _finish(lines)


def _order(text: str, side_match: re.Match[str], memory: Any, paper: bool) -> Optional[str]:
    """Run, explain or refuse the order in ``text``; ``None`` if there isn't one."""
    side = "buy" if side_match.group("buy") else "sell"
    if not paper and _NOT_A_REQUEST.match(side_match.group(0)):
        return None
    after = text[side_match.end():]
    dollars = _DOLLAR_ORDER.match(after)
    if dollars:
        amount = float((dollars.group("amount") or dollars.group("spelled")).replace(",", ""))
        query = _instrument_query(after[dollars.end():])
        return _dollar_order(side, amount, query, paper, bool(_SHARE_WORDS.search(text)))
    everything = _ALL_SHARES.match(after)
    quantity: Optional[Union[int, float]]
    if everything:
        quantity, rest = None, after[everything.end():]
    else:
        quantity, rest = _leading_quantity(after)
    query = _instrument_query(rest)
    if quantity is None and not everything:
        trailing = _TRAILING_QUANTITY.match(after)
        name = _instrument_query(trailing.group("name")) if trailing else ""
        if name and resolve_instrument(name, fuzzy=paper):
            quantity = int(trailing.group("qty").replace(",", ""))
            query, rest = name, ""
    item = resolve_instrument(query, fuzzy=paper) if query else None
    if item is None:
        code = _IDENTIFIER.search(after)
        item = resolve_instrument(code.group("code"), fuzzy=False) if code else None
    if item is None and not query and isinstance(quantity, int):
        item = resolve_instrument(str(quantity), fuzzy=False)
        if item is not None:
            quantity = None
    sell_all = bool(everything) and side == "sell"
    if not paper:
        if (quantity is None and not sell_all) or (item is None and not _SHARE_WORDS.search(text)):
            return None
        if item is None:
            example = _command(side, None if sell_all else _example_quantity(quantity), "AAPL")
            return _real_trade_reply(example, False)
        return _real_trade_reply(_command(side, quantity, item.symbol), True)
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
    portfolio = load_portfolio(memory)
    if sell_all:
        quantity = _held(portfolio, item.symbol)
        if not quantity:
            return _rejected_reply(NOT_ENOUGH_SHARES, side, 0, item, portfolio)
    if quantity is None:
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
    order = {"symbol": item.symbol, "side": side, "quantity": quantity}
    updated, error = execute_order(portfolio, order)
    if error:
        return _rejected_reply(error, side, quantity, item, portfolio)
    save_portfolio(memory, updated)
    return _fill_reply(side, int(quantity), item, updated)


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
    named = _mentioned_instruments(message)
    portfolio_words = _PORTFOLIO.search(message)
    if portfolio_words and not named:
        return _portfolio_reply(load_portfolio(memory))
    search = _SEARCH.search(message)
    if search:
        query = _query_after(message, search.end())
        if query:
            return _lookup_reply(query)
        return _list_reply("OpenTrading's demo stocks and indices:", INSTRUMENTS, INDICES)
    indices = _INDICES.search(message)
    if indices:
        query = _query_after(message, indices.end())
        found = search_indices(query)
        if not found:
            return _finish([
                f'No demo index matches "{query}". The demo indices are '
                + ", ".join(f"{index.name} ({index.code})" for index in INDICES) + ".",
            ])
        return _list_reply("Demo market indices from OpenTrading:", (), found)
    quote = _QUOTE.search(message)
    if quote:
        query = _query_after(message, quote.end())
        item = resolve_instrument(query) if query else None
        if item is not None:
            return _quote_reply(item)
        if len(named) == 1:
            return _quote_reply(named[0])
        if named:
            return _list_reply("Demo quotes from OpenTrading:", named)
        if query:
            return _lookup_reply(query)
        return _list_reply("OpenTrading's demo stocks:", INSTRUMENTS)
    if portfolio_words:
        return _portfolio_reply(load_portfolio(memory))
    return None


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
                    f"{_usd(STARTING_CASH)}, or give the order on its own, e.g. paper buy 10 AAPL.",
                ])
            if _QUESTION.match(message):
                return _finish([
                    f"To start again with {_usd(STARTING_CASH)} of paper cash and no positions, "
                    "say: reset my paper portfolio",
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
    """How to paper trade, with examples that work offline."""
    return _finish([
        "Paper trading with OpenTrading's demo stocks: practise with "
        f"{_usd(STARTING_CASH)} of pretend cash. Try:",
        "- paper buy 10 AAPL",
        "- paper sell 5 shares of Apple",
        "- simulate buying 3 Microsoft",
        "- show my paper portfolio",
        "- paper quote AAPL",
        "- look up ISIN US0378331005",
        "- paper indices",
        "- reset my paper portfolio",
        _demo_list(),
        "Orders are whole shares from 1 to 10,000 at the demo price; you can't spend "
        "more cash than you have or sell shares you don't hold.",
    ])
