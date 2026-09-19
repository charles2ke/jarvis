"""An offline economics reference, money calculator and financial coach.

The glossary follows the same shape as :mod:`jarvis.maritime`: plain data
looked up by title or alias with a forgiving fallback. On top of it sit two
extras — :func:`solve_money` for everyday money arithmetic (compound
interest, loan payments, inflation, budgets) and :func:`advice` for the
general guidance a financial coach would give.

Nothing here is personalised financial advice: it is general education, and
every coaching answer says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Callable, Dict, List, Optional, Sequence, Tuple

DISCLAIMER = (
    "This is general financial education, not personalised advice — for "
    "decisions about your own money, check with a qualified adviser."
)


@dataclass(frozen=True)
class Entry:
    """A single economics or personal finance reference entry."""

    title: str
    summary: str
    aliases: Sequence[str] = field(default_factory=tuple)

    @property
    def keys(self) -> Tuple[str, ...]:
        return (self.title, *self.aliases)


ENTRIES: Tuple[Entry, ...] = (
    Entry(
        title="Economics",
        summary=(
            "Economics studies how people, firms and governments use scarce "
            "resources. Microeconomics looks at single markets — how prices "
            "settle where supply meets demand — while macroeconomics looks at "
            "the whole economy: output, employment, inflation and trade."
        ),
        aliases=("economy", "economic science", "microeconomics", "macroeconomics"),
    ),
    Entry(
        title="Supply and demand",
        summary=(
            "Demand falls as prices rise and supply grows as prices rise; the "
            "market clears at the price where the two meet. Shifts in income, "
            "tastes, input costs or technology move the curves, which is why "
            "shortages push prices up and gluts push them down."
        ),
        aliases=("demand", "supply", "law of supply and demand", "market price"),
    ),
    Entry(
        title="Inflation",
        summary=(
            "Inflation is a sustained rise in the general price level, so each "
            "unit of currency buys less. It is measured by index baskets such "
            "as the consumer price index, and most central banks aim for about "
            "2 percent a year. Deflation is the opposite and is usually worse, "
            "because falling prices delay spending and raise real debts."
        ),
        aliases=(
            "deflation",
            "cpi",
            "consumer price index",
            "cost of living",
            "hyperinflation",
        ),
    ),
    Entry(
        title="GDP",
        summary=(
            "Gross domestic product is the market value of everything produced "
            "inside a country in a period. Nominal GDP uses current prices; "
            "real GDP strips inflation out so growth is comparable over time. "
            "GDP per capita divides it by population, and it deliberately "
            "ignores unpaid work, inequality and environmental damage."
        ),
        aliases=(
            "gross domestic product",
            "real gdp",
            "nominal gdp",
            "gdp per capita",
            "economic growth",
        ),
    ),
    Entry(
        title="Recession",
        summary=(
            "A recession is a broad, sustained fall in economic activity — "
            "often shorthanded as two consecutive quarters of falling real "
            "GDP, though dating committees look at output, employment and "
            "income together. Expansions and recessions together make the "
            "business cycle; a long, deep one is called a depression."
        ),
        aliases=("depression", "business cycle", "economic downturn", "slump"),
    ),
    Entry(
        title="Interest rates",
        summary=(
            "An interest rate is the price of borrowing money, quoted per "
            "year. Central banks set a policy rate to steer inflation and "
            "employment: raising it cools borrowing and spending, cutting it "
            "encourages both. The real interest rate is the nominal rate minus "
            "inflation, and it is what actually matters to savers."
        ),
        aliases=(
            "interest rate",
            "policy rate",
            "base rate",
            "real interest rate",
            "nominal interest rate",
        ),
    ),
    Entry(
        title="Compound interest",
        summary=(
            "Compound interest pays interest on interest, so balances grow "
            "exponentially: a sum at rate r for n years becomes P(1+r)^n. The "
            "rule of 72 estimates the doubling time — 72 divided by the "
            "percentage rate. It works just as hard against you on credit card "
            "debt as it works for you on savings."
        ),
        aliases=("compounding", "rule of 72", "simple interest", "compound growth"),
    ),
    Entry(
        title="Central bank",
        summary=(
            "A central bank issues the currency, sets the policy interest "
            "rate, supervises banks and acts as lender of last resort. The "
            "Federal Reserve, European Central Bank, Bank of England and Bank "
            "of Japan are the largest; most operate with an inflation target "
            "and day-to-day independence from government."
        ),
        aliases=(
            "monetary policy",
            "federal reserve",
            "the fed",
            "european central bank",
            "quantitative easing",
        ),
    ),
    Entry(
        title="Fiscal policy",
        summary=(
            "Fiscal policy is the government's use of tax and spending. A "
            "deficit means spending exceeds revenue in a year and is financed "
            "by borrowing; the accumulated deficits are the national debt. "
            "Fiscal policy is usually judged against debt as a share of GDP "
            "rather than in absolute money."
        ),
        aliases=(
            "budget deficit",
            "national debt",
            "government debt",
            "taxation",
            "austerity",
            "stimulus",
        ),
    ),
    Entry(
        title="Stocks and shares",
        summary=(
            "A share is part ownership of a company; its return comes from "
            "dividends and from price changes. Shares have historically beaten "
            "cash and bonds over long periods, with much larger falls along "
            "the way, so they suit money you will not need for years."
        ),
        aliases=(
            "stock",
            "stocks",
            "shares",
            "equities",
            "equity",
            "stock market",
            "dividend",
        ),
    ),
    Entry(
        title="Bonds",
        summary=(
            "A bond is a loan to a government or company that pays a fixed "
            "coupon and returns its face value at maturity. Prices move "
            "opposite to interest rates, and longer bonds move more. The yield "
            "is the return implied by today's price; credit risk is the chance "
            "the issuer does not pay."
        ),
        aliases=("bond", "fixed income", "gilts", "treasuries", "yield", "coupon"),
    ),
    Entry(
        title="Index funds and ETFs",
        summary=(
            "An index fund tracks a whole market rather than picking stocks, "
            "so it buys broad diversification for a very low fee; an ETF is "
            "the same idea traded like a share. Costs compound as surely as "
            "returns do, which is why a low expense ratio is one of the few "
            "reliable edges a small investor has."
        ),
        aliases=(
            "index fund",
            "etf",
            "etfs",
            "tracker fund",
            "passive investing",
            "mutual fund",
            "expense ratio",
        ),
    ),
    Entry(
        title="Diversification",
        summary=(
            "Diversification spreads money across assets, sectors and "
            "countries so no single failure is fatal. It lowers risk without "
            "lowering expected return, which is why it is called the only free "
            "lunch in finance. Asset allocation — the split between shares, "
            "bonds and cash — drives most of a portfolio's behaviour."
        ),
        aliases=(
            "asset allocation",
            "portfolio",
            "risk tolerance",
            "rebalancing",
            "free lunch",
        ),
    ),
    Entry(
        title="Emergency fund",
        summary=(
            "An emergency fund is three to six months of essential spending "
            "held in cash you can reach the same day. It exists so that a "
            "broken car or a lost job does not become credit card debt, so it "
            "is kept boring and liquid rather than invested."
        ),
        aliases=("rainy day fund", "emergency savings", "safety net", "cash buffer"),
    ),
    Entry(
        title="Budgeting",
        summary=(
            "A budget is a plan for the money you already have. The 50/30/20 "
            "rule is a simple frame: about half of take-home pay for needs, "
            "thirty percent for wants and twenty percent for saving and debt "
            "repayment. Paying yourself first — automating the saving on "
            "payday — beats relying on willpower at the end of the month."
        ),
        aliases=(
            "budget",
            "50/30/20",
            "50 30 20 rule",
            "zero based budget",
            "pay yourself first",
        ),
    ),
    Entry(
        title="Debt repayment",
        summary=(
            "Two orders work. The avalanche pays the highest interest rate "
            "first and costs the least; the snowball clears the smallest "
            "balance first and keeps motivation up. Either way, keep minimum "
            "payments on everything, and clear high-rate debt before investing "
            "for anything except a pension match."
        ),
        aliases=(
            "debt snowball",
            "debt avalanche",
            "paying off debt",
            "credit card debt",
            "debt",
        ),
    ),
    Entry(
        title="Credit score",
        summary=(
            "A credit score summarises how reliably you repay. Payment history "
            "and how much of your available credit you use matter most, "
            "followed by the age of your accounts. Paying on time and keeping "
            "card balances well under the limit does almost all the work."
        ),
        aliases=("credit rating", "credit report", "credit utilisation", "fico"),
    ),
    Entry(
        title="Mortgages",
        summary=(
            "A mortgage is a loan secured on property, repaid over decades. "
            "Early payments are mostly interest, later ones mostly capital. A "
            "larger deposit, a shorter term or a lower rate each cut the total "
            "interest sharply, and overpayments come straight off the capital."
        ),
        aliases=("mortgage", "home loan", "amortisation", "amortization", "refinance"),
    ),
    Entry(
        title="Retirement saving",
        summary=(
            "Retirement saving works on time, contributions and cost. Take any "
            "employer match first — it is an immediate return no market "
            "offers — use tax-advantaged accounts such as a 401(k), IRA or "
            "workplace pension, and keep fees low. The 4 percent rule is a "
            "rough guide: a pot of about 25 times annual spending."
        ),
        aliases=(
            "retirement",
            "pension",
            "401k",
            "401(k)",
            "ira",
            "employer match",
            "4 percent rule",
        ),
    ),
    Entry(
        title="Insurance",
        summary=(
            "Insurance transfers risks you cannot absorb — health, disability, "
            "a dependent family, a home — to someone who can, in exchange for "
            "a premium. Insure the catastrophes and self-insure the small "
            "stuff by raising excesses and keeping an emergency fund."
        ),
        aliases=("premium", "life insurance", "health insurance", "deductible"),
    ),
    Entry(
        title="Taxes",
        summary=(
            "Most income tax systems are progressive: a higher rate applies "
            "only to the income above each threshold, so a raise never leaves "
            "you worse off overall. Your marginal rate is what the next pound "
            "or dollar is taxed at; your effective rate is total tax divided "
            "by total income."
        ),
        aliases=(
            "tax",
            "income tax",
            "marginal tax rate",
            "effective tax rate",
            "tax bracket",
            "capital gains tax",
        ),
    ),
    Entry(
        title="Opportunity cost",
        summary=(
            "Opportunity cost is the value of the best option you gave up. It "
            "is the core idea of economics: money and time spent one way "
            "cannot be spent another. Sunk costs — money already spent and "
            "unrecoverable — should never influence the next decision."
        ),
        aliases=("sunk cost", "trade-off", "scarcity"),
    ),
    Entry(
        title="Exchange rates",
        summary=(
            "An exchange rate is the price of one currency in another. Floating "
            "rates move with trade flows, interest rates and expectations; "
            "pegged rates are held by a central bank. A weaker currency makes "
            "exports cheaper abroad and imports dearer at home."
        ),
        aliases=(
            "exchange rate",
            "foreign exchange",
            "forex",
            "currency",
            "devaluation",
        ),
    ),
    Entry(
        title="Unemployment",
        summary=(
            "The unemployment rate counts people without work who are "
            "available and looking, as a share of the labour force. It misses "
            "discouraged workers who stopped looking, so economists also watch "
            "the participation rate. Some unemployment is frictional — people "
            "moving between jobs — and never reaches zero."
        ),
        aliases=(
            "unemployment rate",
            "jobless rate",
            "labour force",
            "labor force",
            "full employment",
        ),
    ),
)


_STOPWORD_PREFIX = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)


def _normalise(text: str) -> str:
    """Return a comparable form of ``text`` for lookups."""

    cleaned = text.strip().lower()
    cleaned = re.sub(r"[^\w\s'/-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = _STOPWORD_PREFIX.sub("", cleaned)
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


# --------------------------------------------------------------------------
# Money maths
# --------------------------------------------------------------------------

_NUMBER = r"[-+]?\d[\d,]*(?:\.\d+)?"
_MULTIPLIERS = {"k": 1_000.0, "m": 1_000_000.0, "bn": 1_000_000_000.0, "b": 1_000_000_000.0}


def _number(text: str) -> float:
    """Parse ``text`` as a number, allowing thousands separators and k/m/bn."""

    cleaned = text.strip().lower().replace(",", "").replace("$", "").replace("£", "")
    cleaned = cleaned.replace("€", "").strip()
    match = re.fullmatch(r"([-+]?\d*\.?\d+)\s*(k|m|bn|b)?", cleaned)
    if match is None:
        raise ValueError(f"'{text}' is not a number I can read.")
    value = float(match.group(1))
    suffix = match.group(2)
    if suffix:
        value *= _MULTIPLIERS[suffix]
    return value


def _money(value: float) -> str:
    """Format ``value`` as a plain amount with thousands separators."""

    return f"{value:,.2f}"


def _rate(text: str) -> float:
    """Parse a percentage such as ``5`` or ``5.5%`` as a decimal fraction."""

    return _number(text.replace("%", "")) / 100.0


def compound_interest(
    principal: float, annual_rate: float, years: float, *, contribution: float = 0.0
) -> float:
    """Return the future value of ``principal`` plus monthly ``contribution``.

    ``annual_rate`` is a decimal fraction (0.05 for 5 percent) and interest
    compounds monthly.
    """

    months = years * 12
    monthly = annual_rate / 12
    if monthly == 0:
        return principal + contribution * months
    growth = (1 + monthly) ** months
    return principal * growth + contribution * (growth - 1) / monthly


def loan_payment(principal: float, annual_rate: float, years: float) -> float:
    """Return the level monthly payment that repays ``principal``."""

    months = years * 12
    if months <= 0:
        raise ValueError("A loan needs a term of at least one month.")
    monthly = annual_rate / 12
    if monthly == 0:
        return principal / months
    return principal * monthly / (1 - (1 + monthly) ** -months)


def real_value(amount: float, annual_inflation: float, years: float) -> float:
    """Return what ``amount`` will be worth after inflation."""

    return amount / ((1 + annual_inflation) ** years)


def rule_of_72(annual_rate: float) -> float:
    """Return the approximate number of years for money to double."""

    if annual_rate <= 0:
        raise ValueError("Doubling needs a positive rate.")
    return 72 / (annual_rate * 100)


def budget_5030_20(income: float) -> Tuple[float, float, float]:
    """Return the 50/30/20 split of ``income``: needs, wants, savings."""

    return income * 0.5, income * 0.3, income * 0.2


def _solve_compound(match: re.Match[str]) -> str:
    principal = _number(match.group("principal"))
    rate = _rate(match.group("rate"))
    years = _number(match.group("years"))
    contribution = 0.0
    raw_contribution = match.groupdict().get("contribution")
    if raw_contribution:
        contribution = _number(raw_contribution)
    total = compound_interest(principal, rate, years, contribution=contribution)
    paid_in = principal + contribution * years * 12
    lines = [
        f"Saving {_money(principal)} at {rate * 100:g}% a year"
        + (f" plus {_money(contribution)} a month" if contribution else "")
        + f" for {years:g} years grows to about {_money(total)}.",
        f"You put in {_money(paid_in)}, so {_money(total - paid_in)} is growth "
        "(monthly compounding).",
    ]
    return "\n".join(lines)


def _solve_loan(match: re.Match[str]) -> str:
    principal = _number(match.group("principal"))
    rate = _rate(match.group("rate"))
    years = _number(match.group("years"))
    payment = loan_payment(principal, rate, years)
    total = payment * years * 12
    return (
        f"A {_money(principal)} loan at {rate * 100:g}% over {years:g} years costs "
        f"about {_money(payment)} a month.\n"
        f"That is {_money(total)} repaid in total, {_money(total - principal)} of it "
        "interest."
    )


def _solve_inflation(match: re.Match[str]) -> str:
    amount = _number(match.group("amount"))
    rate = _rate(match.group("rate"))
    years = _number(match.group("years"))
    worth = real_value(amount, rate, years)
    return (
        f"With {rate * 100:g}% inflation, {_money(amount)} in {years:g} years buys "
        f"what {_money(worth)} buys today — a loss of {_money(amount - worth)} in "
        "purchasing power."
    )


def _solve_doubling(match: re.Match[str]) -> str:
    rate = _rate(match.group("rate"))
    years = rule_of_72(rate)
    return (
        f"By the rule of 72, money at {rate * 100:g}% a year doubles in about "
        f"{years:.1f} years."
    )


def _solve_budget(match: re.Match[str]) -> str:
    income = _number(match.group("income"))
    needs, wants, savings = budget_5030_20(income)
    return (
        f"On {_money(income)} a month the 50/30/20 split is {_money(needs)} for "
        f"needs, {_money(wants)} for wants and {_money(savings)} for saving and "
        "extra debt repayments.\n"
        "Automate the saving on payday so it happens before the spending does."
    )


def _solve_emergency_fund(match: re.Match[str]) -> str:
    spending = _number(match.group("spending"))
    return (
        f"On essentials of {_money(spending)} a month, aim for {_money(spending * 3)} "
        f"to {_money(spending * 6)} in an easy-access account.\n"
        "Three months is usually enough with a steady salary; six or more if your "
        "income varies or others depend on you."
    )


_SOLVERS: Tuple[Tuple[str, Callable[[re.Match[str]], str]], ...] = (
    (
        r"(?:invest|save|grow|put)\D{0,20}(?P<principal>" + _NUMBER + r"(?:\s?(?:k|m|bn)\b)?)"
        r"\D{0,25}?(?P<rate>" + _NUMBER + r")\s*(?:%|percent)"
        r"\D{0,30}?(?P<years>" + _NUMBER + r")\s*(?:years?|yrs?)"
        r"(?:\D{0,30}?(?P<contribution>" + _NUMBER + r"(?:\s?(?:k|m)\b)?)\s*(?:a|per|each)\s*month)?",
        _solve_compound,
    ),
    (
        r"(?:compound\s+interest|future\s+value)\D{0,20}(?P<principal>"
        + _NUMBER
        + r"(?:\s?(?:k|m|bn)\b)?)\D{0,25}?(?P<rate>"
        + _NUMBER
        + r")\s*(?:%|percent)\D{0,30}?(?P<years>"
        + _NUMBER
        + r")\s*(?:years?|yrs?)",
        _solve_compound,
    ),
    (
        r"(?:monthly\s+payment|repayment|mortgage|loan|borrow)\D{0,25}(?P<principal>"
        + _NUMBER
        + r"(?:\s?(?:k|m)\b)?)\D{0,25}?(?P<rate>"
        + _NUMBER
        + r")\s*(?:%|percent)\D{0,30}?(?P<years>"
        + _NUMBER
        + r")\s*(?:years?|yrs?)",
        _solve_loan,
    ),
    (
        r"inflation\D{0,30}?(?P<rate>" + _NUMBER + r")\s*(?:%|percent)"
        r"\D{0,30}?(?P<amount>" + _NUMBER + r"(?:\s?(?:k|m|bn)\b)?)"
        r"\D{0,30}?(?P<years>" + _NUMBER + r")\s*(?:years?|yrs?)",
        _solve_inflation,
    ),
    (
        r"(?P<amount>" + _NUMBER + r"(?:\s?(?:k|m|bn)\b)?)\D{0,25}?worth\D{0,25}?"
        r"(?P<years>" + _NUMBER + r")\s*(?:years?|yrs?)\D{0,30}?(?P<rate>"
        + _NUMBER
        + r")\s*(?:%|percent)\s*inflation",
        _solve_inflation,
    ),
    (
        r"(?:double|doubling)\D{0,40}?(?P<rate>" + _NUMBER + r")\s*(?:%|percent)",
        _solve_doubling,
    ),
    (
        r"(?:50/30/20|50 30 20|budget)\D{0,40}?(?P<income>" + _NUMBER + r"(?:\s?(?:k|m)\b)?)",
        _solve_budget,
    ),
    (
        r"emergency\s+fund\D{0,40}?(?P<spending>" + _NUMBER + r"(?:\s?(?:k|m)\b)?)",
        _solve_emergency_fund,
    ),
)

_COMPILED_SOLVERS = tuple(
    (re.compile(pattern, re.IGNORECASE), handler) for pattern, handler in _SOLVERS
)


def solve_money(text: str) -> Optional[str]:
    """Answer an everyday money question, or return ``None``.

    Handles compound growth, loan and mortgage payments, the effect of
    inflation, the rule of 72, the 50/30/20 budget and emergency fund
    sizing.
    """

    if not text:
        return None
    for pattern, handler in _COMPILED_SOLVERS:
        found = pattern.search(text)
        if found is None:
            continue
        try:
            return handler(found)
        except (ValueError, ZeroDivisionError, OverflowError):
            continue
    return None


# --------------------------------------------------------------------------
# Coaching
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Guidance:
    """A financial coaching answer for one kind of money question."""

    topic: str
    headline: str
    steps: Sequence[str]
    triggers: Sequence[str] = field(default_factory=tuple)

    def format(self) -> str:
        lines = [self.headline]
        lines.extend(f"- {step}" for step in self.steps)
        lines.append(DISCLAIMER)
        return "\n".join(lines)


GUIDANCE: Tuple[Guidance, ...] = (
    Guidance(
        topic="Getting out of debt",
        headline="Here is how I would approach paying down debt:",
        steps=(
            "List every debt with its balance, rate and minimum payment.",
            "Keep every minimum payment going so nothing defaults.",
            "Put spare money on the highest rate first (avalanche, cheapest) or "
            "the smallest balance first (snowball, most motivating).",
            "Ask about a lower rate, a balance transfer or consolidation — but "
            "only if you stop adding to the balance.",
            "Keep a small cash buffer so the next surprise does not go back on "
            "the card.",
        ),
        triggers=(
            "debt",
            "credit card",
            "loan",
            "owe",
            "overdraft",
            "pay off",
            "payoff",
        ),
    ),
    Guidance(
        topic="Budgeting",
        headline="A budget you will actually keep looks like this:",
        steps=(
            "Work out take-home pay and the essentials it must cover.",
            "Try 50/30/20 — needs, wants, saving and debt — and adjust to your "
            "real numbers.",
            "Automate saving on payday, so it happens before the spending.",
            "Track for one month to find the leaks; most budgets fail on "
            "irregular costs, so give annual bills a monthly line.",
            "Review quarterly rather than daily — it is a plan, not a diet.",
        ),
        triggers=("budget", "spending", "overspend", "paycheck", "pay cheque", "expenses"),
    ),
    Guidance(
        topic="Saving",
        headline="Saving works best in this order:",
        steps=(
            "Build one month of essentials as a starter buffer.",
            "Take any employer pension or 401(k) match — it is free money.",
            "Clear high-interest debt, which is a guaranteed return.",
            "Top the emergency fund up to three to six months of essentials, in "
            "cash you can reach the same day.",
            "Then invest what you will not need for five years or more.",
        ),
        triggers=("save", "saving", "savings", "emergency fund", "rainy day"),
    ),
    Guidance(
        topic="Investing",
        headline="The boring investing basics that tend to work:",
        steps=(
            "Only invest money you will not need for at least five years.",
            "Use broad, low-cost index funds rather than picking stocks.",
            "Diversify across regions and asset classes; keep fees low, because "
            "they compound too.",
            "Invest regularly on a schedule instead of timing the market.",
            "Match risk to your horizon, and expect large falls along the way.",
        ),
        triggers=(
            "invest",
            "investing",
            "investment",
            "stocks",
            "shares",
            "etf",
            "index fund",
            "portfolio",
            "crypto",
        ),
    ),
    Guidance(
        topic="Retirement",
        headline="Retirement saving comes down to time, contributions and cost:",
        steps=(
            "Take the full employer match before anything else.",
            "Use tax-advantaged accounts — pension, 401(k), IRA or local "
            "equivalent.",
            "Aim to save around 15 percent of gross pay, including the match.",
            "Keep fund fees low and leave the money invested.",
            "Sanity-check the target with the 4 percent rule: roughly 25 times "
            "your annual spending.",
        ),
        triggers=("retire", "retirement", "pension", "401k", "401(k)", "ira"),
    ),
    Guidance(
        topic="Buying a home",
        headline="Before taking on a mortgage:",
        steps=(
            "Budget on the total monthly cost — payment, insurance, tax, "
            "maintenance — not just the payment.",
            "A bigger deposit cuts the rate and the total interest, often "
            "sharply.",
            "Keep the emergency fund intact after the deposit.",
            "Compare the whole cost of the deal, not only the headline rate, "
            "and check early repayment terms.",
            "Buy for how long you will stay; costs of moving eat short-term "
            "gains.",
        ),
        triggers=("mortgage", "buy a house", "buying a house", "buy a home", "deposit", "first home"),
    ),
    Guidance(
        topic="Income and career money",
        headline="On earning more:",
        steps=(
            "Raising income usually beats trimming spending, once the budget is "
            "sane.",
            "Research the market rate for your role before any pay conversation.",
            "Bank the raise: send at least half of any increase straight to "
            "saving before lifestyle absorbs it.",
            "Keep a record of results, not just duties, for the next review.",
            "Check the whole package — pension, bonus, insurance — not the "
            "headline salary.",
        ),
        triggers=("raise", "salary", "earn more", "side hustle", "income", "pay rise"),
    ),
    Guidance(
        topic="Money worry",
        headline="Money stress is real, and a plan helps more than worry does:",
        steps=(
            "Write down what is actually owed and what actually comes in — "
            "vagueness makes it feel worse.",
            "Cover the essentials first: housing, food, utilities, minimum "
            "payments.",
            "Talk to lenders early; most have hardship options that are far "
            "better than missed payments.",
            "Look up what support or benefits you are entitled to.",
            "Take one action this week rather than solving everything tonight.",
        ),
        triggers=(
            "broke",
            "struggling",
            "worried about money",
            "money stress",
            "cannot afford",
            "can't afford",
            "paycheck to paycheck",
            "bills",
        ),
    ),
)


GENERAL_ADVICE = Guidance(
    topic="Money basics",
    headline="The short version of personal finance:",
    steps=(
        "Spend less than you earn, and know the gap.",
        "Keep three to six months of essentials in cash.",
        "Clear high-interest debt before investing.",
        "Take every employer pension match.",
        "Invest the long-term money in low-cost, diversified funds and leave it "
        "alone.",
        "Insure what you cannot afford to lose.",
    ),
)


def advice(text: str) -> str:
    """Return coaching for the money topic in ``text``."""

    lowered = (text or "").lower()
    best: Optional[Guidance] = None
    best_score = 0
    for guidance in GUIDANCE:
        score = sum(len(trigger) for trigger in guidance.triggers if trigger in lowered)
        if score > best_score:
            best, best_score = guidance, score
    return (best or GENERAL_ADVICE).format()
