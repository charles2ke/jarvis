"""Estimate income tax on a salary with the user's tax-break project.

tax-break (https://charles2ke.github.io/tax-break/, source at
https://github.com/charles2ke/tax-break) is the user's own tax calculator,
built around a TypeScript tax engine. Jarvis keeps no copy of its rules: every
figure in a reply comes from that engine in the ``projects/tax-break``
submodule, run with Node.js by ``bridges/tax-break.mjs``. The Indian financial
years and US states the engine offers, and the web app's one-line description
of each country's calculator, come from the project too and are read once per
session.

:func:`estimate` reads a free-text request such as "income tax on 15 lakh in
India" or "UK take-home on £3,000 a month" itself — salary, period, country,
year, regime, deductions, filing status and so on — then asks the engine about
that salary and about 1,000 more, for the marginal rate, in one Node.js run.
It returns ``None`` when the text isn't a salary tax question, so the caller
can try something else; that check needs neither the project nor Node.js, and
nor does :func:`usage`. Nothing here is tax advice.

When the project or Node.js is missing, :func:`estimate` raises
:class:`jarvis.projects.ProjectUnavailable` with setup steps.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

from jarvis import projects

PROJECT = "tax-break"
SITE_URL = projects.PROJECTS[PROJECT].site
REPO_URL = projects.PROJECTS[PROJECT].repo
CREDIT = f"From {PROJECT}: {SITE_URL}"
DISCLAIMER = (
    "This is an estimate for general education, not tax advice — check with "
    "the tax authority or a qualified adviser."
)


# --------------------------------------------------------------------------
# The project
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class _Meta:
    """What the engine offers: Indian years, US states and calculator descriptions."""

    years: Tuple[Tuple[str, str], ...]  # (key, label)
    states: Tuple[Tuple[str, str], ...]  # (two-letter code, name)
    taglines: Tuple[Tuple[str, str], ...]  # (country key, description)

    @property
    def latest_year(self) -> str:
        return max(key for key, _label in self.years)

    def year_label(self, key: str) -> str:
        return dict(self.years)[key]

    def state_name(self, code: str) -> str:
        return dict(self.states)[code]

    def tagline(self, country: str) -> str:
        return dict(self.taglines).get(country, "")


_YEAR_KEY = re.compile(r"FY\d{4}-\d{2}")
_STATE_CODE = re.compile(r"[A-Z]{2}")


def _entries(data: Any, key: str, fields: Tuple[str, str]) -> Tuple[Tuple[str, str], ...]:
    items = data.get(key) if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise projects.ProjectError(f"tax-break listed no {key}")
    rows = []
    for item in items:
        first, second = (item.get(name) if isinstance(item, dict) else None for name in fields)
        if not all(isinstance(value, str) and value.strip() for value in (first, second)):
            raise projects.ProjectError(f"tax-break's {key} have no usable {' or '.join(fields)}")
        rows.append((first.strip(), second.strip()))
    return tuple(rows)


@lru_cache(maxsize=1)
def _meta() -> _Meta:
    """Read the years, states and calculator descriptions from tax-break (once per process)."""

    data = projects.call(PROJECT, "meta")
    years = _entries(data, "years", ("key", "label"))
    if not all(_YEAR_KEY.fullmatch(key) for key, _label in years):
        raise projects.ProjectError("tax-break's Indian years aren't keyed the way Jarvis expects")
    states = _entries(data, "states", ("code", "name"))
    if not all(_STATE_CODE.fullmatch(code) for code, _name in states):
        raise projects.ProjectError("tax-break's US states don't all have two-letter codes")
    # The descriptions are only shown, so a missing one just isn't.
    countries = data.get("countries")
    taglines = []
    for item in countries if isinstance(countries, list) else ():
        if isinstance(item, dict):
            value, tagline = item.get("value"), item.get("tagline")
            if isinstance(value, str) and isinstance(tagline, str) and tagline.strip():
                taglines.append((value, " ".join(tagline.split())))
    return _Meta(years, states, tuple(taglines))


def _number(data: Any, *path: str) -> float:
    """The finite number at ``path`` in an engine result."""

    value = data
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise projects.ProjectError(f"tax-break's result has no usable {'.'.join(path)}")
    return float(value)


def _calculate(action: str, inputs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Run one of the adapter's calculations on each input, in one Node.js run."""

    results = projects.call(PROJECT, action, {"inputs": list(inputs)})
    if not (
        isinstance(results, list)
        and len(results) == len(inputs)
        and all(isinstance(result, dict) for result in results)
    ):
        raise projects.ProjectError(f"tax-break's {action} results don't match the request")
    return results


# --------------------------------------------------------------------------
# Plain-text replies
# --------------------------------------------------------------------------

_SYMBOLS: Dict[str, str] = {
    "india": "₹", "uk": "£", "us": "$", "ireland": "€", "netherlands": "€", "singapore": "S$",
}
# The marginal rate is the extra tax on this much more salary.
_STEP = 1000.0
_INDIA_AGE_TEXT: Dict[str, str] = {
    "below60": "below 60", "60to80": "aged 60 to 79", "above80": "aged 80 or over",
}
_SINGAPORE_AGE_TEXT: Dict[str, str] = {
    "below55": "below 55", "55to59": "aged 55 to 59", "60plus": "aged 60 or over",
}
_UK_PLAN_NAMES: Dict[str, str] = {
    "plan1": "Plan 1", "plan2": "Plan 2", "plan4": "Plan 4", "plan5": "Plan 5",
    "postgraduate": "Postgraduate Loan",
}
_US_STATUS_TEXT: Dict[str, str] = {
    "single": "single filer", "marriedJoint": "married filing jointly",
    "marriedSeparate": "married filing separately", "headOfHousehold": "head of household",
}
_IRELAND_STATUS_TEXT: Dict[str, str] = {
    "single": "single PAYE employee",
    "singleParent": "single parent, PAYE employee",
    "marriedOneIncome": "married or civil partners with one income, PAYE employee",
}
# (name in replies, Jarvis's claim keys, the engine's deduction)
_INDIA_DEDUCTIONS: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    ("80C", ("section_80c",), "section80C"),
    ("80D", ("section_80d_self", "section_80d_parents"), "section80D"),
    ("NPS 80CCD(1B)", ("section_80ccd1b",), "section80CCD1B"),
    ("80E", ("section_80e",), "section80E"),
    ("80G", ("section_80g",), "section80G"),
)


def _india_age(age: Optional[int]) -> str:
    if age is None or age < 60:
        return "below60"
    return "60to80" if age < 80 else "above80"


def _singapore_age(age: Optional[int]) -> str:
    if age is None or age < 55:
        return "below55"
    return "55to59" if age < 60 else "60plus"


def _group_indian(digits: str) -> str:
    """Group a digit string the Indian way: 1500000 becomes 15,00,000."""

    head, tail = digits[:-3], digits[-3:]
    groups: List[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


def _money(value: float, symbol: str, *, whole: bool = False) -> str:
    """Format money with ``symbol`` and separators (lakh/crore for ₹); cents only if any."""

    size = abs(value)
    cents = math.floor(size + 0.5) * 100 if whole else math.floor(size * 100 + 0.5)
    units, fraction = divmod(cents, 100)
    digits = _group_indian(str(units)) if symbol == "₹" else f"{units:,}"
    text = symbol + digits + (f".{fraction:02d}" if fraction else "")
    return "-" + text if value < 0 and cents else text


def _pct(value: float) -> str:
    """A percentage to one decimal place, without a trailing ".0"."""

    if abs(value) < 0.05:
        return "0%"
    return f"{value:.1f}".rstrip("0").rstrip(".") + "%"


def _assumptions(parts: Sequence[str]) -> str:
    return "Assumptions: " + ", ".join(parts) + "."


def _income_phrase(req: "_Request", symbol: str) -> str:
    """Describe the salary as asked, e.g. "₹1,00,000 a month (₹12,00,000 a year)"."""

    annual = _money(req.salary, symbol)
    if req.period in ("month", "week"):
        text = f"{_money(req.stated, symbol)} a {req.period} ({annual} a year)"
    else:
        text = f"{annual} a year"
    if req.bonus:
        text += f" plus a {_money(req.bonus, symbol)} bonus ({_money(req.income, symbol)} in all)"
    return text


def _per_year_line(label: str, amount: float, req: "_Request", symbol: str, suffix: str = "") -> str:
    if req.period == "week":
        per = f"about {_money(amount / 52, symbol, whole=True)} a week"
    else:
        per = f"about {_money(amount / 12, symbol, whole=True)} a month"
    return f"- {label}: {_money(amount, symbol)} a year, {per}{suffix}"


def _rates_line(symbol: str, income: float, total: float, next_total: float) -> str:
    """Tax as a share of the income, and the share of the next _STEP that goes in tax."""

    effective = total / income * 100 if income > 0 else 0.0
    marginal = (next_total - total) / _STEP * 100
    line = (
        f"- Rates: {_pct(effective)} effective, {_pct(marginal)} marginal on the next "
        f"{_money(_STEP, symbol)}"
    )
    if marginal >= 60:
        line += " (a threshold is crossed here, or an allowance, credit or relief tapers off)"
    return line


def _finish(lines: Sequence[str], notes: Sequence[str] = (), *, disclaimer: bool = True) -> str:
    out = list(lines)
    if notes:
        out.append("Notes:")
        out.extend(f"- {note}" for note in dict.fromkeys(notes))
    if disclaimer:
        out.append(DISCLAIMER)
    out.append(CREDIT)
    return "\n".join(out)


def _claim_suffix(claimed: float, allowed: float, symbol: str) -> str:
    if math.isinf(claimed):
        return " (the maximum)"
    if claimed > allowed + 0.005:
        return f" (capped from {_money(claimed, symbol)})"
    return ""


def _age_note(calculator: str, example: str) -> str:
    return (
        f"tax-break's {calculator} calculator doesn't take an age, so age-based rules such as "
        f"{example} aren't applied."
    )


def _calculator_line(meta: _Meta, country: str) -> List[str]:
    """The web app's own description of the calculator used, which may name its year."""

    tagline = meta.tagline(country)
    return [f'Calculator: tax-break for {_COUNTRY_NAMES[country]} — "{tagline}"'] if tagline else []


def _totals(
    lines: List[str], req: "_Request", symbol: str, result: Dict[str, Any], next_total: float,
    label: str = "Take-home", suffix: str = "",
) -> float:
    """Add the total, take-home and rates lines for an international estimate."""

    total = _number(result, "totalTaxLiability")
    lines.append(f"- Total: {_money(total, symbol)}")
    lines.append(_per_year_line(label, _number(result, result["country"], "netIncome"), req, symbol, suffix))
    lines.append(_rates_line(symbol, req.income, total, next_total))
    return total


def _fy(key: str) -> str:
    """A year key such as "FY2024-25" written as "FY 2024-25"."""

    return "FY " + key[2:]


def _year_decline(meta: _Meta, asked: str) -> str:
    keys = sorted(key for key, _label in meta.years)
    held = _fy(keys[0]) + (f" to {_fy(keys[-1])}" if len(keys) > 1 else " only")
    return _finish(
        [
            f"tax-break has Indian tables for {held}, not {asked}, so I can't estimate that year.",
            f"Ask without a year to use {meta.year_label(meta.latest_year)}, the latest it has.",
        ],
        disclaimer=False,
    )


# India: the engine compares both regimes for the salary and for _STEP more.

def _india_input(req: "_Request", fy: str, age: str, salary: float) -> Dict[str, Any]:
    def claim(*keys: str) -> Any:
        value = sum(req.deductions.get(key, 0.0) for key in keys)
        return "max" if math.isinf(value) else value

    data: Dict[str, Any] = {
        "assessmentYear": fy,
        "ageCategory": age,
        "salary": {
            "basic": salary, "hraReceived": 0, "rentPaid": 0, "cityType": "metro", "lta": 0,
            "specialAllowance": 0, "otherTaxableAllowances": req.bonus,
        },
    }
    if any(value > 0 for key, value in req.deductions.items() if key != "home_loan_interest"):
        data["deductions"] = {
            "section80C": claim("section_80c"),
            "section80D": {
                "selfAndFamilyPremium": claim("section_80d_self"),
                "parentsPremium": claim("section_80d_parents"),
                "selfSenior": age != "below60",
                "parentsSenior": req.parents_senior,
            },
            "section80CCD1B": claim("section_80ccd1b"),
            "section80E": claim("section_80e"),
            "section80G": claim("section_80g"),
        }
    if req.deductions.get("home_loan_interest", 0.0) > 0:
        data["houseProperty"] = {
            "type": "self-occupied", "homeLoanInterest": claim("home_loan_interest"),
        }
    return data


def _regimes(result: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    regimes = {regime: result.get(regime) for regime in ("new", "old")}
    if not all(isinstance(value, dict) for value in regimes.values()):
        raise projects.ProjectError("tax-break's comparison is missing a regime")
    return regimes  # type: ignore[return-value]


def _deductions_unused(result: Dict[str, Any]) -> bool:
    """True when a regime's figure used no deduction but the standard one."""

    return (
        _number(result, "totalDeductions")
        <= _number(result, "deductionsBreakdown", "standardDeduction") + 0.005
        and _number(result, "grossTotalIncome") >= _number(result, "taxableSalaryIncome") - 0.005
    )


def _india_block(result: Dict[str, Any], req: "_Request", next_total: float) -> List[str]:
    symbol = _SYMBOLS["india"]
    lines: List[str] = []
    claimed = req.deductions
    used = not _deductions_unused(result)
    interest = claimed.get("home_loan_interest", 0.0)
    set_off = _number(result, "taxableSalaryIncome") - _number(result, "grossTotalIncome")
    if interest > 0 and set_off > 0:
        lines.append(
            f"- Home-loan interest 24(b): {_money(set_off, symbol)} set off against salary"
            + _claim_suffix(interest, set_off, symbol)
        )
    standard = _number(result, "deductionsBreakdown", "standardDeduction")
    total_deductions = _number(result, "totalDeductions")
    rows = [
        (name, sum(claimed.get(key, 0.0) for key in keys), field_name)
        for name, keys, field_name in _INDIA_DEDUCTIONS
    ]
    rows = [row for row in rows if row[1] > 0]
    if used and rows:
        parts = [f"standard {_money(standard, symbol)}"]
        for name, amount, field_name in rows:
            allowed = _number(result, "deductionsBreakdown", field_name)
            parts.append(f"{name} {_money(allowed, symbol)}" + _claim_suffix(amount, allowed, symbol))
        lines.append("- Deductions: " + ", ".join(parts))
        basis = f"after {_money(total_deductions, symbol)} of deductions"
    elif total_deductions > standard + 0.005:
        basis = f"after {_money(total_deductions, symbol)} of deductions"
    elif standard > 0:
        basis = f"after the {_money(standard, symbol)} standard deduction"
    else:
        basis = "no standard deduction"
    lines.append(f"- Taxable income: {_money(_number(result, 'taxableIncome'), symbol)} ({basis})")
    lines.append(f"- Tax on slabs: {_money(_number(result, 'taxBeforeRebate'), symbol)}")
    rebate = _number(result, "rebate")
    if rebate > 0:
        lines.append(f"- Less rebate u/s 87A: {_money(rebate, symbol)}")
    surcharge, relief = _number(result, "surcharge"), _number(result, "marginalRelief")
    if surcharge > 0 or relief > 0:
        line = f"- Surcharge: {_money(surcharge, symbol)}"
        if relief > 0:
            line += f" after {_money(relief, symbol)} marginal relief"
        lines.append(line)
    cess = _number(result, "cess")
    if cess > 0:
        lines.append(f"- Health and education cess: {_money(cess, symbol)}")
    total = _number(result, "totalTaxLiability")
    lines.append(f"- Total tax: {_money(total, symbol)}")
    lines.append(_per_year_line("After income tax", req.income - total, req, symbol))
    lines.append(_rates_line(symbol, req.income, total, next_total))
    return lines


def _india_reply(req: "_Request", meta: _Meta, fy: str, defaulted: bool, notes: List[str]) -> str:
    symbol = _SYMBOLS["india"]
    age = _india_age(req.age)
    now, more = _calculate(
        "india",
        [_india_input(req, fy, age, req.salary), _india_input(req, fy, age, req.salary + _STEP)],
    )
    regimes, next_regimes = _regimes(now), _regimes(more)
    shown = ("new", "old") if req.regime is None else (req.regime,)
    claimed = any(value > 0 for value in req.deductions.values())
    assumptions = [f"resident individual {_INDIA_AGE_TEXT[age]}", "salary income only"]
    if not claimed:
        assumptions.append("no deductions beyond the standard deduction")
    lines = [
        f"Indian income tax on {_income_phrase(req, symbol)}",
        f"Financial year: {meta.year_label(fy)}"
        + (", the latest in tax-break's tables." if defaulted else "."),
        _assumptions(assumptions),
    ]
    for regime in shown:
        lines.append(f"{regime.capitalize()} regime:")
        lines.extend(
            _india_block(regimes[regime], req, _number(next_regimes[regime], "totalTaxLiability"))
        )
    totals = {regime: _number(result, "totalTaxLiability") for regime, result in regimes.items()}
    if req.regime is None:
        recommended = now.get("recommendedRegime")
        if recommended not in totals:
            raise projects.ProjectError("tax-break's comparison names no regime")
        if totals["old"] == totals["new"]:
            lines.append("Both regimes come to the same tax.")
        else:
            lines.append(
                f"The {recommended} regime is lower by {_money(_number(now, 'savings'), symbol)} a year."
            )
    else:
        other = "old" if req.regime == "new" else "new"
        lines.append(f"For comparison, the {other} regime comes to {_money(totals[other], symbol)}.")

    extra = list(notes)
    if claimed and shown == ("new",) and _deductions_unused(regimes["new"]):
        extra.append(
            "The new-regime figure uses none of the deductions you gave; the old-regime "
            "comparison includes them."
        )
    if not claimed and "old" in shown:
        extra.append(
            "Old-regime deductions such as 80C, 80D, NPS 80CCD(1B) and home-loan interest 24(b) "
            'would lower the old figure; add them, e.g. "80C 1 lakh".'
        )
    donation = req.deductions.get("section_80g", 0.0)
    if (
        "old" in shown and 0 < donation < math.inf
        and _number(regimes["old"], "deductionsBreakdown", "section80G") >= donation - 0.005
    ):
        extra.append(
            "tax-break deducted the whole 80G donation; many donations qualify for only 50% or "
            "are capped."
        )
    if _HRA.search(req.text):
        extra.append(
            "I didn't include an HRA exemption, so the old-regime figure may be too high if you "
            "claim one."
        )
    if _CTC.search(req.text):
        extra.append(
            "The CTC is treated as taxable salary; employer PF and other untaxed parts of a CTC "
            "would lower the tax."
        )
    if _MARRIED.search(req.text):
        extra.append("Indian income tax is assessed per person; this is for one salary.")
    extra.append("After income tax is before EPF and professional tax.")
    return _finish(lines, extra)


# The other countries: one engine estimate for the salary and one for _STEP more.

def _international_input(req: "_Request", country: str, **options: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {"country": country, "annualIncome": req.salary}
    data.update((key, value) for key, value in options.items() if value is not None)
    if req.bonus:
        data["bonus"] = req.bonus
    return data


def _checked(result: Dict[str, Any], country: str) -> Dict[str, Any]:
    if result.get("country") != country or not isinstance(result.get(country), dict):
        raise projects.ProjectError(f"tax-break's estimate isn't for {_COUNTRY_NAMES[country]}")
    return result


def _international(req: "_Request", country: str, **options: Any) -> Tuple[Dict[str, Any], float]:
    """The engine's estimate for the salary, and its total on _STEP more."""

    data = _international_input(req, country, **options)
    now, more = _calculate(
        "international", [data, dict(data, annualIncome=req.salary + _STEP)]
    )
    return _checked(now, country), _number(_checked(more, country), "totalTaxLiability")


def _uk_plan(text: str) -> Tuple[Optional[str], List[str]]:
    """Read a student loan plan from ``text``; returns the plan key and any notes."""

    notes: List[str] = []
    plans: List[str] = []
    for match in _UK_PLAN.finditer(text):
        number = _NUMBER_WORDS.get(match.group("plan").lower(), match.group("plan"))
        plans.append({"1": "plan1", "2": "plan2", "3": "postgraduate", "4": "plan4", "5": "plan5"}[number])
        if number == "3":
            notes.append("I took Plan 3 as the Postgraduate Loan.")
    if _UK_POSTGRAD.search(text):
        plans.append("postgraduate")
    unique = list(dict.fromkeys(plans))
    if not unique:
        if _STUDENT_LOAN.search(text):
            notes.append('Say which student loan plan you have, e.g. "plan 2", to include repayments.')
        return None, notes
    if len(unique) > 1:
        notes.append(
            f"I can give tax-break one student loan plan at a time, so I used "
            f"{_UK_PLAN_NAMES[unique[0]]} only."
        )
    return unique[0], notes


def _uk_reply(req: "_Request", meta: _Meta, notes: List[str]) -> str:
    symbol = _SYMBOLS["uk"]
    plan, plan_notes = _uk_plan(req.text)
    result, next_total = _international(req, "uk", studentLoanPlan=plan)
    assumptions = ["England, Wales or Northern Ireland rates", "salary only"]
    if plan is None:
        assumptions.append("no student loan")
    assumptions.append("no pension contributions")
    lines = [f"UK tax on {_income_phrase(req, symbol)}"]
    lines += _calculator_line(meta, "uk")
    lines += [
        _assumptions(assumptions),
        f"- Personal allowance: {_money(_number(result, 'uk', 'personalAllowance'), symbol)}",
        f"- Taxable income: {_money(_number(result, 'taxableIncome'), symbol)}",
        f"- Income tax: {_money(_number(result, 'incomeTax'), symbol)}",
        f"- National Insurance: {_money(_number(result, 'uk', 'nationalInsurance'), symbol)}",
    ]
    if plan:
        repayment = _number(result, "uk", "studentLoanRepayment")
        lines.append(f"- Student loan ({_UK_PLAN_NAMES[plan]}): {_money(repayment, symbol)}")
    _totals(lines, req, symbol, result, next_total)

    extra = list(notes) + plan_notes
    if _PENSION.search(req.text):
        extra.append(
            "Pension contributions aren't deducted; salary sacrifice or relief at source would "
            "lower the tax."
        )
    if req.age is not None:
        extra.append(_age_note("UK", "employee National Insurance ending at State Pension age"))
    if _KIDS.search(req.text):
        extra.append(
            "Child Benefit isn't included, nor the High Income Child Benefit Charge that takes "
            "it back on higher incomes."
        )
    if _MARRIED.search(req.text):
        extra.append("UK income tax is per person; this is for one salary.")
    return _finish(lines, extra)


def _scotland_reply(req: "_Request") -> str:
    symbol = _SYMBOLS["uk"]
    (result,) = _calculate("international", [_international_input(req, "uk")])
    ni = _number(_checked(result, "uk"), "uk", "nationalInsurance")
    return _finish([
        "Scotland sets its own income tax bands and rates, which tax-break doesn't have, so I "
        "can't estimate Scottish income tax.",
        f"National Insurance is UK-wide: on {_income_phrase(req, symbol)}, tax-break puts it at "
        f"{_money(ni, symbol)}.",
        "Ask about England, Wales or Northern Ireland for a full UK estimate.",
    ])


def _us_status(text: str) -> Tuple[str, List[str]]:
    if _US_MFS.search(text):
        return "marriedSeparate", []
    if _US_HOH.search(text):
        return "headOfHousehold", []
    if _US_MFJ.search(text):
        return "marriedJoint", []
    if _MARRIED.search(text) and not _SINGLE.search(text):
        return "marriedJoint", ['I assumed married filing jointly; say "filing separately" if not.']
    return "single", []


def _us_reply(req: "_Request", meta: _Meta, state: Optional[str], notes: List[str]) -> str:
    symbol = _SYMBOLS["us"]
    status, status_notes = _us_status(req.text)
    data = _international_input(
        req, "us", filingStatus=status, dependentsUnder17=req.children or None, state=state,
    )
    inputs = [data, dict(data, annualIncome=req.salary + _STEP)]
    # A single filer's state tax, to tell whether tax-break's state figure reflects the status.
    if state and status != "single":
        inputs.append(dict(data, filingStatus="single"))
    results = [_checked(found, "us") for found in _calculate("international", inputs)]
    result, next_total = results[0], _number(results[1], "totalTaxLiability")
    assumptions = [_US_STATUS_TEXT[status], "standard deduction", "wages only"]
    if not state:
        assumptions.append("no state tax")
    lines = [f"US tax on {_income_phrase(req, symbol)}" + (f" in {meta.state_name(state)}" if state else "")]
    lines += _calculator_line(meta, "us")
    lines += [
        _assumptions(assumptions),
        f"- Taxable income: {_money(_number(result, 'taxableIncome'), symbol)} "
        f"(after the {_money(_number(result, 'standardDeduction'), symbol)} standard deduction)",
        f"- Federal income tax: {_money(_number(result, 'incomeTax'), symbol)}",
    ]
    credits = _number(result, "taxCredits")
    if req.children:
        kids = f"{req.children} {'child' if req.children == 1 else 'children'} under 17"
        lines.append(f"- Less child tax credit: {_money(credits, symbol)} ({kids})")
    elif credits > 0:
        lines.append(f"- Less tax credits: {_money(credits, symbol)}")
    lines.append(f"- FICA: {_money(_number(result, 'us', 'ficaTax'), symbol)}")
    medicare = _number(result, "us", "additionalMedicareTax")
    if medicare > 0:
        lines.append(f"- Additional Medicare tax: {_money(medicare, symbol)}")
    if state:
        state_tax = _number(result, "stateTax")
        if state_tax > 0:
            base = _money(_number(result, "stateTaxableIncome"), symbol)
            lines.append(
                f"- {meta.state_name(state)} income tax: {_money(state_tax, symbol)} "
                f"(on {base} of state taxable income)"
            )
        else:
            lines.append(f"- {meta.state_name(state)} income tax: none")
    _totals(lines, req, symbol, result, next_total)

    extra = list(notes) + status_notes
    if state is None:
        extra.append('Add a state for state income tax, e.g. "in California".')
    elif len(results) > 2:
        state_tax = _number(result, "stateTax")
        if state_tax > 0 and abs(_number(results[2], "stateTax") - state_tax) < 0.005:
            extra.append(
                f"tax-break's {meta.state_name(state)} figure is the same as a single filer's, "
                f"so a {_US_STATUS_TEXT[status]} return there may differ."
            )
    if req.children:
        extra.append("I assumed the children are under 17.")
        full = _number(result, "us", "childTaxCredit")
        if credits <= 0 < full:
            extra.append(
                f"The child tax credit would be {_money(full, symbol)}, but there's no federal "
                "income tax here for it to reduce; a refundable part, if any, isn't included."
            )
        elif credits < full - 0.005:
            extra.append(
                f"The child tax credit would be {_money(full, symbol)}, but only "
                f"{_money(credits, symbol)} of it is set against the federal income tax here; a "
                "refundable part, if any, isn't included."
            )
    elif _KIDS.search(req.text) and not req.children_stated:
        extra.append("Say how many children under 17 you have to include the child tax credit.")
    if req.age is not None:
        extra.append(_age_note("US", "the larger standard deduction for older filers"))
    if _PENSION.search(req.text):
        extra.append("401(k), IRA and other pre-tax contributions aren't deducted.")
    return _finish(lines, extra)


def _ireland_status(text: str) -> str:
    if _IE_SINGLE_PARENT.search(text):
        return "singleParent"
    return "marriedOneIncome" if _MARRIED.search(text) else "single"


def _ireland_reply(req: "_Request", meta: _Meta, notes: List[str]) -> str:
    symbol = _SYMBOLS["ireland"]
    status = _ireland_status(req.text)
    result, next_total = _international(req, "ireland", filingStatus=status)
    cut_off = _money(_number(result, "ireland", "standardRateCutOff"), symbol)
    lines = [f"Irish tax on {_income_phrase(req, symbol)}"]
    lines += _calculator_line(meta, "ireland")
    lines += [
        _assumptions([_IRELAND_STATUS_TEXT[status], "salary only"]),
        f"- Gross tax: {_money(_number(result, 'incomeTax'), symbol)} "
        f"(standard rate cut-off point {cut_off})",
        f"- Less tax credits: {_money(_number(result, 'taxCredits'), symbol)}",
        f"- USC: {_money(_number(result, 'ireland', 'universalSocialCharge'), symbol)}",
        f"- PRSI: {_money(_number(result, 'ireland', 'prsi'), symbol)}",
    ]
    _totals(lines, req, symbol, result, next_total)

    extra = list(notes)
    if status == "marriedOneIncome":
        extra.append("For a married couple or civil partners I assumed one income.")
    if req.age is not None:
        extra.append(_age_note("Irish", "the age tax credit"))
    if _PENSION.search(req.text):
        extra.append("Pension contributions aren't deducted.")
    return _finish(lines, extra)


def _netherlands_reply(req: "_Request", meta: _Meta, notes: List[str]) -> str:
    symbol = _SYMBOLS["netherlands"]
    result, next_total = _international(
        req, "netherlands", thirtyPercentRuling=True if req.ruling else None
    )
    lines = [f"Dutch tax on {_income_phrase(req, symbol)}"]
    lines += _calculator_line(meta, "netherlands")
    lines.append(_assumptions(["salary only", "30% ruling applied" if req.ruling else "no 30% ruling"]))
    if req.ruling:
        exempt = _number(result, "netherlands", "thirtyPercentExemption")
        lines.append(f"- 30% ruling: {_money(exempt, symbol)} tax-free")
    lines.append(f"- Box 1 income: {_money(_number(result, 'netherlands', 'box1Income'), symbol)}")
    lines.append(f"- Box 1 tax: {_money(_number(result, 'netherlands', 'box1Tax'), symbol)}")
    credits = _number(result, "taxCredits")
    general = _number(result, "netherlands", "generalTaxCredit")
    labour = _number(result, "netherlands", "labourTaxCredit")
    detail = f"general {_money(general, symbol)}, labour {_money(labour, symbol)}"
    if credits < general + labour - 0.005:
        detail += ", limited to the tax"
    lines.append(f"- Less tax credits: {_money(credits, symbol)} ({detail})")
    _totals(lines, req, symbol, result, next_total)

    extra = list(notes)
    if req.ruling:
        extra.append("I didn't check whether you meet the 30% ruling's conditions.")
    if _HOLIDAY.search(req.text):
        extra.append(
            "Holiday allowance (vakantiegeld) is taxable; include it in the salary if it's paid "
            "on top."
        )
    if req.age is not None:
        extra.append(_age_note("Dutch", "the lower rates from State Pension (AOW) age"))
    if _PENSION.search(req.text):
        extra.append("Pension contributions aren't deducted.")
    if _MARRIED.search(req.text):
        extra.append("Dutch income tax is per person; this is for one salary.")
    return _finish(lines, extra)


def _singapore_reply(req: "_Request", meta: _Meta, notes: List[str]) -> str:
    symbol = _SYMBOLS["singapore"]
    band = _singapore_age(req.age)
    result, next_total = _international(
        req, "singapore", ageBand=band,
        reliefs={"cpfContributions": req.cpf} if req.cpf else None,
    )
    lines = [f"Singapore income tax on {_income_phrase(req, symbol)}"]
    lines += _calculator_line(meta, "singapore")
    lines.append(_assumptions([
        f"tax resident {_SINGAPORE_AGE_TEXT[band]}", "employment income only",
        "earned income and CPF relief" if req.cpf else "earned income relief only",
    ]))
    allowed = _number(result, "singapore", "totalReliefsAllowed")
    if _number(result, "singapore", "totalReliefsBeforeCap") > allowed + 0.005:
        basis = f"after reliefs, capped at {_money(allowed, symbol)}"
    elif req.cpf:
        basis = f"after {_money(allowed, symbol)} of earned income and CPF relief"
    else:
        relief = _number(result, "singapore", "earnedIncomeRelief")
        basis = f"after {_money(relief, symbol)} earned income relief"
    chargeable = _number(result, "singapore", "chargeableIncome")
    lines.append(f"- Chargeable income: {_money(chargeable, symbol)} ({basis})")
    lines.append(f"- Income tax: {_money(_number(result, 'incomeTax'), symbol)}")
    rebate = _number(result, "singapore", "taxRebate")
    if rebate > 0:
        lines.append(f"- Less tax rebate: {_money(rebate, symbol)}")
    after_tax = req.income - _number(result, "totalTaxLiability")
    untouched = abs(_number(result, "singapore", "netIncome") - after_tax) < 0.005
    _totals(
        lines, req, symbol, result, next_total, "After income tax",
        " (CPF contributions not deducted)" if untouched else "",
    )

    extra = list(notes)
    if not req.cpf:
        extra.append('Employee CPF contributions also get relief; add them, e.g. "CPF of S$12,000".')
    return _finish(lines, extra)


# --------------------------------------------------------------------------
# Reading a question
# --------------------------------------------------------------------------

COUNTRIES: Tuple[str, ...] = (
    "India", "United Kingdom", "United States", "Ireland", "Netherlands", "Singapore",
)
_COVERAGE = (
    "India, the UK (England, Wales and Northern Ireland), the US, Ireland, the Netherlands "
    "and Singapore"
)
_EXAMPLES: Dict[str, str] = {
    "india": "income tax on ₹15,00,000 in India",
    "uk": "UK tax on £50,000",
    "us": "US tax on $85,000 in California",
    "ireland": "Irish tax on €60,000",
    "netherlands": "Dutch tax on €70,000",
    "singapore": "Singapore tax on S$120,000",
}
_COUNTRY_NAMES: Dict[str, str] = {
    "india": "India", "uk": "the UK", "us": "the US", "ireland": "Ireland",
    "netherlands": "the Netherlands", "singapore": "Singapore",
}
_COUNTRY_ADJECTIVES: Dict[str, str] = {
    "india": "Indian", "uk": "UK", "us": "US", "ireland": "Irish",
    "netherlands": "Dutch", "singapore": "Singapore",
}
_LOCAL_CURRENCY: Dict[str, str] = {
    "india": "rupees", "uk": "pounds", "us": "US dollars", "ireland": "euros",
    "netherlands": "euros", "singapore": "Singapore dollars",
}
_CURRENCY_NAMES: Dict[str, str] = {
    "inr": "rupees", "gbp": "pounds", "usd": "US dollars", "dollar": "dollars",
    "eur": "euros", "sgd": "Singapore dollars",
}
_CURRENCY_SYMBOLS: Dict[str, str] = {
    "inr": "₹", "gbp": "£", "usd": "US$", "dollar": "$", "eur": "€", "sgd": "S$",
}
_ACCEPTED_CURRENCIES: Dict[str, Tuple[str, ...]] = {
    "india": ("inr",), "uk": ("gbp",), "us": ("usd", "dollar"), "ireland": ("eur",),
    "netherlands": ("eur",), "singapore": ("sgd", "dollar"),
}
_CURRENCY_COUNTRY: Dict[str, str] = {
    "inr": "india", "gbp": "uk", "usd": "us", "sgd": "singapore",
}
_MAX_TEXT = 1000
_MAX_INCOME = 1e10

# Patterns the reply builders read from the cleaned, lower-cased question.
_HRA = re.compile(r"\bhra\b|house rent allowance")
_CTC = re.compile(r"\bctc\b|cost to (?:the )?company")
_MARRIED = re.compile(
    r"(?<!ex-)(?<!ex )\b(?:married|marriage|wife|husband|spouse|civil partner(?:ship)?|newlywed)\b"
)
_SINGLE = re.compile(r"\b(?:single|unmarried|divorced|widow(?:ed|er)?|separated)\b")
_UK_PLAN = re.compile(
    r"\bplan\s*(?P<plan>[1-5]|one|two|three|four|five)\b"
    r"(?!\s*(?:%|percent|per\s*cent|k\b|,\d|\.\d))"
)
_NUMBER_WORDS: Dict[str, str] = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
}
_UK_POSTGRAD = re.compile(
    r"\b(?:post[- ]?grad(?:uate)?|masters?'?|doctoral|phd)\s+(?:student\s+)?loans?\b|\bpgl\b"
)
_STUDENT_LOAN = re.compile(r"\bstudent\s+(?:loans?|finance)\b|\bslc\b")
_PENSION = re.compile(
    r"(?<![$£€₹])\b(?:pensions?|401\s*\(?k\)?|403\s*\(?b\)?|457\s*\(?b\)?|ira|roth|retirement|"
    r"superannuation|salary sacrifice|kiwisaver|rrsp)(?![a-z0-9])"
)
_KIDS = re.compile(
    r"\b(?:kids?|child(?:ren)?|sons?|daughters?|bab(?:y|ies)|toddlers?|depend[ae]nts?|twins|triplets)\b"
)
_US_MFS = re.compile(
    r"\b(?:married\s+)?fil(?:e|ing)\s+separate(?:ly)?\b|\bseparate\s+(?:tax\s+)?returns?\b|\bmfs\b"
)
_US_HOH = re.compile(r"\bhead\s+of\s+(?:the\s+)?household\b|\bhoh\b")
_US_MFJ = re.compile(
    r"\b(?:married\s+)?fil(?:e|ing)\s+(?:a\s+)?joint(?:ly)?\b"
    r"|\bjoint(?:ly)?\s+(?:tax\s+)?(?:returns?|filing|filers?)\b"
    r"|\bmfj\b"
)
_IE_SINGLE_PARENT = re.compile(
    r"\b(?:single|lone)\s+(?:parent|mum|mom|mother|father|dad)\b|\bone[- ]parent family\b"
    r"|\bchild carer\b"
)
_HOLIDAY = re.compile(r"\bholiday\s+(?:allowance|pay)\b|\bvakantie(?:geld|toeslag)\b")


@dataclass
class _Request:
    """A parsed question: the salary and the details the reply builders need."""

    text: str
    salary: float
    stated: float
    period: str = "year"
    bonus: float = 0.0
    deductions: Dict[str, float] = field(default_factory=dict)
    parents_senior: bool = False
    regime: Optional[str] = None
    age: Optional[int] = None
    cpf: float = 0.0
    children: int = 0
    children_stated: bool = False
    ruling: bool = False

    @property
    def income(self) -> float:
        return self.salary + self.bonus


@dataclass
class _Amount:
    start: int
    end: int
    value: float
    raw: str = ""
    currency: Optional[str] = None
    period: Optional[str] = None
    implied_inr: bool = False
    multiplied: bool = False
    role: str = "salary"
    keyword: str = ""
    paired: bool = False
    paired_forward_ws: bool = False
    bare_year: bool = False


@dataclass
class _Keyword:
    start: int
    end: int
    role: str
    text: str


@dataclass
class _Facts:
    ruling: bool = False
    ruling_mentioned: bool = False
    age: Optional[int] = None
    parents_senior: bool = False
    children: int = 0
    children_stated: bool = False
    years: List[Tuple[int, str, int, Optional[int]]] = field(default_factory=list)
    hours_per_week: Optional[float] = None


class _Reply(Exception):
    """Raised inside the parser to answer early with a finished reply."""

    def __init__(self, reply: str) -> None:
        super().__init__(reply)
        self.reply = reply


_INVISIBLE = re.compile("[\u200b-\u200d\u2060\ufeff\u00ad]")
_SINGLE_QUOTES = re.compile("[\u2018\u2019\u201a\u201b\u2032\u02bc]")
_DOUBLE_QUOTES = re.compile("[\u201c-\u201f\u2033]")
_DASHES = re.compile("[\u2010-\u2015\u2212]")
_ESCAPES = re.compile(r"\\[nrt]")
_NOT_MARRIED = re.compile(
    r"\b(?:not|never(?:\s+been)?|isn't|aren't|wasn't)\s+(?:yet\s+|been\s+)?married\b"
)


def _clean(text: str) -> Tuple[str, str]:
    """Return the question with tidy whitespace and punctuation, and a lower-cased copy."""

    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", text)
    text = _SINGLE_QUOTES.sub("'", text)
    text = _DOUBLE_QUOTES.sub('"', text)
    text = _DASHES.sub("-", text)
    text = _ESCAPES.sub(" ", text)
    original = " ".join(text.split())
    return original, _NOT_MARRIED.sub("single", original.lower())


def _blank(text: str, start: int, end: int) -> str:
    return text[:start] + "\x00" * (end - start) + text[end:]


_INTENT = re.compile(
    r"\b(?:income[- ]?tax(?:es)?|tax(?:es|ed|ation)?|take[- ]?home|"
    r"net\s+(?:pay|salary|income|wages?|earnings)|after[- ]tax|post[- ]tax|national\s+insurance|"
    r"fica|usc|prsi|paye)\b"
)
_IN_HAND = re.compile(r"\bin[- ]hand\b")
_IN_HAND_PAY = re.compile(
    r"(?:\b|(?<=\d))(?:salary|salaries|pay|income|ctc|package|lpa|earn(?:s|ed|ing)?|wages?|stipend)\b"
)

_OTHER_TAX_KINDS = (
    r"sales|vat|gst|hst|pst|qst|value[- ]added|capital[- ]gains?|cgt|property|council|stamp|"
    r"inheritance|estate|death|gift|wealth|corporation|corporate|company|business|franchise|"
    r"dividends?|withholding|excise|import|export|customs|road|car|vehicle|fuel|petrol|gas|carbon|"
    r"land|transfer|crypto|rental|rent|lottery|gambling|tips?|tourist|luxury|sugar|soda|windfall|"
    r"interest|savings|investment|pension|annuity|severance|sin|tobacco|alcohol|poll|toll|"
    r"services?|digital\s+services|entertainment"
)
_OTHER_TAX = re.compile(
    r"\b(?:" + _OTHER_TAX_KINDS + r")(?:\s+income)?[\s-]+tax(?:es|ed|ation)?\b"
    r"(?!\s+(?:benefits?|deductions?|relief|exemptions?|savings?|breaks?|credits?|rebates?|free))"
    r"|\b(?:vat|gst|hst|stamp\s+duty|tariffs?|customs(?:\s+duty)?|excise(?:\s+duty)?|sales\s+tax)\b"
)
_SELF_EMPLOYED = re.compile(
    r"\bself[\s-]?employ\w*|\bfreelanc\w*|\bsole\s+(?:trader|proprietor\w*)"
    r"|\bindependent\s+contractors?\b|\bcontractors?\s+(?:income|rate|day\s+rate)\b"
    r"|(?<![$£€₹\d,.])\b1099\b(?!,?\d|\.\d|\s*(?:a|an|per|each|every)\s|\s*/"
    r"|\s*(?:k|pounds?|dollars?|euros?|rupees?|bucks|quid)\b)"
    r"|\bir35\b"
    r"|\b(?:have|own|run|through)\s+(?:an?\s+|my\s+(?:own\s+)?)?"
    r"(?:llc|limited\s+company|ltd\s+company|ltd)\b"
    r"|\bmy\s+(?:own\s+)?(?:llc|limited\s+company|ltd(?:\s+company)?|business)\b"
    r"|\bmy\s+own\s+company\b"
    r"|\bbusiness\s+(?:income|profits?|owner)\b|\bside\s+(?:hustle|gig|business)\b"
    r"|\bgig\s+(?:work(?:er)?|economy)\b|\bumbrella\s+company\b"
)
_OBJECT_DETERMINERS = (
    r"my|the|a|an|this|that|our|your|his|her|their|some|any|all|these|those|selling|sold|"
    r"sale\s+of|from|of|[$£€₹]?\d[\d,.]*"
    r"(?:\s*(?:k|lakhs?|lacs?|crores?|thousand|grand|m|million|pounds?|dollars?|euros?|rupees?|rs\.?))?"
)
_OBJECTS = (
    r"dividends?|rent(?:al)?(?!\s+allowance)|interest|gains?|shares?|stocks?|rsus?|esops?|"
    r"(?:stock|share)\s+options?|crypto|bitcoin|property|house(?!\s+rent)|home\s+sale|land|"
    r"inheritance|gifts?|savings|investments?|business|profits?|pension|lump\s+sum|severance|"
    r"redundancy|sale|lottery|winnings|royalt(?:y|ies)|tips|freelance|side\s+(?:income|hustle|gig)|"
    r"annuit(?:y|ies)|withdrawals?|car|purchases?|goods|services|groceries|food|bonds?|"
    r"mutual\s+funds?|fds?|fixed\s+deposits?|nfts?|prize|jackpot"
)
_OBJECT_TAX = re.compile(
    r"\btax(?:es|ed|ation)?\s+(?:on|for|of|from)\s+(?:(?:" + _OBJECT_DETERMINERS + r")\s+){0,3}"
    r"(?:" + _OBJECTS + r")\b"
)
_BUDGET = re.compile(
    r"\b(?:budget(?:ing|s)?|afford(?:able)?|mortgage|emergency\s+fund|50/30/20|spend(?:ing)?|spent|"
    r"expenses|expenditure)\b"
)
_CONVERT = re.compile(r"\b(?:convert(?:ed|ing|s)?|conversion|exchange\s+rate)\b")
_FILING = re.compile(
    r"\b(?:refunds?|(?<!joint\s)(?<!separate\s)tax\s+returns?|penalt(?:y|ies)|deadlines?|arrears|"
    r"over-?paid|under-?paid|over-?payment|under-?payment)\b"
)
_PAID = re.compile(
    r"\b(?:paid|pay|paying|pays|owe[sd]?|owing)\s+(?:the\s+(?:irs|hmrc|taxman)\s+)?"
    r"(?:£|\$|€|₹|s\$|rs\.?\s*)?\d(?:[\d,.]*\d)?\s*"
    r"(?:k|lakhs?|lacs?|crores?|thousand|grand|m|million)?\s*"
    r"(?:(?:pounds?|dollars?|euros?|rupees?|bucks|quid)\s+)?(?:(?:in|of|as)\s+)?(?:income\s+)?"
    r"tax(?:es)?\b"
    r"|\b(?:paid|pay|paying|pays|owe[sd]?|owing)\s+(?:(?:my|the|an?|our)\s+)?(?:income\s+)?"
    r"tax(?:es)?(?:\s+bill)?\s+(?:of|worth|amounting\s+to|total(?:l?ing)?)\s+"
    r"(?:£|\$|€|₹|s\$|rs\.?\s*)?\d"
    r"|\bowe[sd]?\s+(?:the\s+)?(?:irs|hmrc|revenue|taxman)\b"
)
_REVERSE = re.compile(
    r"\bgross(?:ing)?[\s-]+up\b|\bnet[\s-]+to[\s-]+gross\b|\breverse\s+(?:tax|salary|calculat\w*)"
    r"|\b(?:need|have|want|required?)\s+to\s+(?:earn|make|be\s+paid|get\s+paid|gross)\b[^?!]*?"
    r"\b(?:to\s+)?(?:take\s+home|net|clear|keep|get|have|bring\s+home|walk\s+away\s+with)\b"
    r"|\b(?:what|which|how\s+much)\s+(?:gross\s+|pre-?tax\s+)?(?:salary|pay|income|ctc|package|gross)\b"
    r"[^?!]*?\b(?:gives?|for\s+(?:a\s+)?net|to\s+(?:take\s+home|net|clear|get|have|bring\s+home)"
    r"|need(?:ed)?|requir\w*)\b"
    r"|\b(?:take[- ]?home|in[- ]hand|net(?:\s+(?:pay|salary|income))?"
    r"|after[- ]tax(?:\s+(?:pay|salary|income))?)"
    r"(?:\s+(?:is|of|will\s+be|should\s+be|needs\s+to\s+be|must\s+be)\b|\s*[=:])[^?!]*?"
    r"\b(?:what|how\s+much|calculate|find|work\s+out)\b[^?!]*?\b(?:gross|ctc|before\s+tax|pre-?tax)\b"
    r"|\b(?:want|need|wish|hope|expect|like)\s+(?:to\s+(?:take\s+home|get|have|net|clear|keep)\s+)?"
    r"(?:[$£€₹]|s\$|rs\.?\s*)?\d[\d,.]*\s*(?:k|lakhs?|lacs?|crores?|thousand|grand|m|million)?\s*"
    r"(?:(?:pounds?|dollars?|euros?|rupees?|bucks|quid)\s+)?(?:(?:a|per|each|every)\s+(?:month|year|week)\s+)?"
    r"(?:after[- ]tax|take[- ]?home|in[- ]hand|net|post[- ]tax|clear)\b"
    r"|\b(?:my|our|the)\s+(?:monthly\s+|annual\s+|yearly\s+|weekly\s+)?(?:take[- ]?home|in[- ]hand|net)"
    r"(?:\s+(?:pay|salary|income))?(?:\s+(?:is|was|will\s+be)|\s*[=:])\s*(?:about\s+|around\s+)?[$£€₹]?\d"
    r"|\b(?:what|which|how\s+much)(?:'s|\s+is)?\s+(?:the\s+|my\s+)?(?:gross|pre-?tax|before[- ]tax)"
    r"(?:\s+(?:salary|pay|income))?\s+(?:for|to|from|if|when|given|needed|required)\b"
)


def _has_intent(low: str) -> bool:
    if _INTENT.search(low):
        return True
    return bool(_IN_HAND.search(low) and _IN_HAND_PAY.search(low))


def _gate(low: str) -> Optional[str]:
    """Return "skip" for questions that aren't salary tax, a reply to answer politely, or None."""

    if _OTHER_TAX.search(low):
        return "skip"
    if _SELF_EMPLOYED.search(low):
        return _finish(
            [
                "I can only estimate tax on a salary (employment income), so I can't do "
                "self-employment, freelance or business income.",
                f'For a salary, ask e.g. "{_EXAMPLES["uk"]}".',
            ],
            disclaimer=False,
        )
    if any(p.search(low) for p in (_OBJECT_TAX, _BUDGET, _CONVERT, _FILING, _PAID)):
        return "skip"
    if _REVERSE.search(low):
        return _finish(
            [
                "I work forward from a gross (before-tax) salary, so I can't start from a "
                "take-home figure.",
                f'Give a gross salary instead, e.g. "{_EXAMPLES["uk"]}".',
            ],
            disclaimer=False,
        )
    return None


# Spans the amount reader must not see: each is blanked with NUL characters so that
# positions in the lower-cased text and the masked copy stay aligned.
_RULING = re.compile(
    r"(?P<neg>\b(?:no|without|not\s+on(?:\s+the)?|not|don'?t\s+have(?:\s+the)?|excluding|w/o)\s+"
    r"(?:a\s+|the\s+|any\s+)?)?"
    r"(?:\b30\s*(?:%|percent|per\s*cent)[\s-]*(?:tax\s+)?(?:ruling|regeling|rule|scheme|facility)\b"
    r"|\bexpat(?:riate)?\s+(?:ruling|scheme)\b|\b(?:the\s+)?ruling\b)"
)
_CONTRIB_WORD = (
    r"(?:pensions?|401\s*\(?k\)?|403\s*\(?b\)?|457\s*\(?b\)?|ira|roth|contribut\w*|sacrific\w*|"
    r"match\w*|cpf|epf|vpf|pf|nps|super(?:annuation)?|kiwisaver|retirement|rrsp|tsp)(?![a-z0-9])"
)
_PCT = r"\d+(?:\.\d+)?\s*(?:%|percent\b|per\s*cent\b)"
_CONTRIB_PCT = re.compile(
    r"\b" + _CONTRIB_WORD + r"(?:\W+\w+){0,5}?\W+(?P<a>" + _PCT + r")"
    r"|(?P<b>" + _PCT + r")(?:\W+\w+){0,5}?\W+" + _CONTRIB_WORD
)
_CODE_BODY = (
    r"80[\s-]?ccd[\s-]*\(?\s*1\s*b\s*\)?|80[\s-]?ccd[\s-]*\(?\s*2\s*\)?|80[\s-]?ccc|80[\s-]?tt[ab]|"
    r"80[\s-]?gg[abc]?|80[\s-]?ddb?|80[\s-]?ee[ab]?|80[\s-]?ccd|80[\s-]?[cdegu]|87-?a|"
    r"24\s*\(\s*b\s*\)|10\s*\(\s*13\s*a\s*\)|10\s*\(\s*14\s*\)|115\s*bac|194(?:i[ab]|la|[achijnqrs])|"
    r"40[13][\s-]*\(?\s*[kb]\s*\)?|457[\s-]*\(?\s*b\s*\)?|form\s*1040(?:-?[a-z]{1,2})?|1099-[a-z]+|"
    r"w-?[24]|p60|p45|p11d|form\s*16a?|26as|itr[\s-]*\d|"
    r"(?:section|sec\.?|u/s)\s*\d+[a-z]*(?:\s*\([^)]*\))?"
)
_CODES = re.compile(
    r"(?<![a-z0-9$£€₹])(?:(?:u/s|under\s+section|section|sec\.?)\s*)?(?:" + _CODE_BODY + r")"
    r"(?![a-z0-9])"
)
_STANDARD_TAX_CODE = re.compile(r"\b1257\s?l\b")
_TAX_CODE_WORDS = re.compile(r"\btax\s+code\b")
_TAX_CODES = re.compile(r"\b[sc]?\d{3,4}[lmnt]\b|\bk\d{1,4}\b")
_HOURS = re.compile(
    r"(?<![\d.,])(?P<h>\d+(?:\.\d+)?)(?P<range>\s*(?:-|to)\s*\d+(?:\.\d+)?)?\s*(?:hours?|hrs?)\b"
    r"(?:\s*(?:(?:a|an|per|each|every)\s+|/\s*)(?P<unit>week|wk|day|month|shift)\b"
    r"|\s*(?P<abbr>pw|pd|pm)\b)?"
)
_MONTHS = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?![a-z])"
)
_MULT_WORDS = (
    r"(?:k\b|lakhs?|lacs?|l\b|crores?|cr\b|thousand|grand|mn?\b|mil\w*|bn\b|billion|%|percent|"
    r"per\s*cent)"
)
_CUR_WORDS = r"(?:euros?|eur\b|pounds?|quid|dollars?|bucks|usd|gbp|inr|sgd|rupees?|rs\b)"
_NOT_MONEY = r"(?!\s*(?:" + _MULT_WORDS + "|" + _CUR_WORDS + r"))"
_DATES = re.compile(
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MONTHS + r"\.?(?:,?\s+\d{4})?"
    r"|\b" + _MONTHS + r"\.?\s+(?:[12]\d|3[01]|0?[1-9])(?:st|nd|rd|th)?\b" + _NOT_MONEY
    + r"(?:,?\s+\d{4})?"
    r"|\b" + _MONTHS + r"\.?\s*,?\s*(?:19|20)\d{2}(?![\d,.]?\d)" + _NOT_MONEY
    + r"|\b(?:since|born|graduated|started|joined)\s+(?:in\s+)?(?:19|20)\d{2}\b"
    r"|(?<![\d.,/-])\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}(?![\d.,/-]?\d)"
    r"|\b\d{4}-\d{2}-\d{2}\b"
    # Decades ("the 1920s") and plurals ("1000s of pounds") are never the salary.
    r"|(?<![\d,.])\b(?:1[89]|20)\d0'?s\b"
    r"|(?<![\d,.])\b(?:[1-9]00|[1-9]\d{0,2}(?:,?000)+)'?s\b"
)
_COUNT_WORDS: Dict[str, int] = {
    "a": 1, "an": 1, "no": 0, "zero": 0,
    **{word: int(digit) for word, digit in _NUMBER_WORDS.items()},
}
_CHILD_NOUNS = (
    r"(?:kids?|child(?:ren)?|sons?|daughters?|bab(?:y|ies)|toddlers?|infants?|newborns?|"
    r"depend[ae]nts?)"
)
_CHILD_COUNT = re.compile(
    r"(?<![\d,.])\b(?P<n>\d{1,2}|" + "|".join(_NUMBER_WORDS) + r"|a|an|no|zero)\s+"
    r"(?:(?:young|little|small|minor|dependent|dependant|qualifying|"
    r"\d{1,2}[\s-]*(?:years?|yrs?)[\s-]*old)\s+)?" + _CHILD_NOUNS + r"\b"
    r"(?!\s+(?:tax|benefit|care|credit|support|allowance|maintenance))"
)
_MULTIPLES = re.compile(r"\b(?:twins|triplets)\b")
_MY_CHILD = re.compile(
    r"\b(?:my|our)\s+(?:(?:young|little|baby|newborn|infant|\d{1,2}[\s-]*(?:years?|yrs?)[\s-]*old)\s+)?"
    r"(?:son|daughter|child|kid|baby|toddler)\b"
)
_CHILD_FIELD = re.compile(r"\b(?:kids|children|dependents|dependants)\s*[:=]\s*(?P<n>\d{1,2})\b")
_PARENT = r"(?:parents?|mother|father|mum|mom|dad|in-?laws?)"
_OP = r"(?:over|above|older\s+than|more\s+than|under|below|younger\s+than|less\s+than)"
_UNDER = ("under", "below", "younger", "less")
_PARENT_AGED = re.compile(r"\b(?P<num>\d{2,3})[\s-]*(?:years?|yrs?)[\s-]*old\s+" + _PARENT + r"\b")
_PARENT_SENIOR = re.compile(
    r"\b(?:senior(?:\s+citizens?)?|elderly|aged|old|older|retired)\s+" + _PARENT + r"\b"
    r"|\b" + _PARENT + r"(?:'s|')?\s+(?:(?:are|is|who\s+are|both|being)\s+)*(?:both\s+)?(?:super\s+)?"
    r"(?:senior(?:\s+citizens?)?|elderly)\b"
)
_PARENT_AGE = re.compile(
    r"\b" + _PARENT + r"(?:'s|')?(?:\s+(?:are|is|aged|both|age|ages|who\s+are)){0,3}\s+"
    r"(?:(?P<op>" + _OP + r")\s+)?(?P<num>\d{2,3})(?![\d,.]?\d)" + _NOT_MONEY
    + r"\+?(?:\s*(?:years?|yrs?)(?:[\s-]*old)?)?"
)
_OWN_AGE = re.compile(
    r"(?<![a-z'])(?P<lead>i'?m|i\s+am|aged|age|turning|i\s+turn(?:ed)?|i'?ll\s+be|i\s+will\s+be)"
    r"\s*:?\s*(?:(?P<op>" + _OP + r")\s+)?(?P<num>\d{2,3})(?![\d,.]?\d)"
    r"(?!\s*(?:" + _MULT_WORDS + "|" + _CUR_WORDS + r"|a\s+(?:year|month|week)|an\s+hour|per\b|/))"
    r"\+?(?:\s*(?:years?|yrs?)(?:[\s-]*old)?)?"
)
_AGE_SUFFIX = re.compile(
    r"\b(?P<num>\d{2,3})(?:[\s-]*(?:years?|yrs?)[\s-]*old|\s+years?\s+of\s+age|\s*y/?o)\b"
)
_KIN = re.compile(
    r"\b(?:kids?|child(?:ren)?|sons?|daughters?|bab(?:y|ies)|toddlers?|depend[ae]nts?|wife|husband|"
    r"spouse|partner|parents?|mother|father|mum|mom|dad|in-?laws?|grand\w+)\b"
)
_SUPER_SENIOR = re.compile(r"\bsuper[\s-]*senior|\bvery\s+senior\s+citizens?\b")
_SENIOR = re.compile(r"\bsenior\s+citizens?\b")
_YEAR_PREFIXED = re.compile(
    r"\b(?P<prefix>f\.?y\.?|a\.?y\.?|y\.?a\.?|financial\s+year|fiscal\s+year|assessment\s+year|"
    r"year\s+of\s+assessment|tax\s+year|income\s+year)\s*[:\-]?\s*(?P<a>\d{4}|\d{2})"
    r"(?:\s*(?:-|/|to)\s*(?P<b>\d{4}|\d{2}))?(?![\d,.]?\d)(?!\s*" + _MULT_WORDS + r")"
)
_YEAR_RANGE = re.compile(
    r"(?<![\d,.])\b(?P<a>(?:19|20)\d{2})\s*(?:-|/|to)\s*(?P<b>(?:19|20)?\d{2})\b(?![,.]?\d)"
)
_YEAR_SHORT = re.compile(r"\b(?P<a>\d{2})/(?P<b>\d{2})\b")
_LEFTOVER_PERCENT = re.compile(r"\d\s*(?:%|percent\b|per\s*cent\b)")


def _second_year(first: int, text: Optional[str]) -> Optional[int]:
    if text is None:
        return None
    if len(text) == 4:
        return int(text)
    value = (first // 100) * 100 + int(text)
    return value + 100 if value < first else value


def _near_kin(low: str, start: int, end: int) -> bool:
    return bool(_KIN.search(low[max(0, start - 25):start]) or _KIN.search(low[end:end + 15]))


def _mask(low: str, facts: _Facts) -> Optional[str]:
    """Blank out everything that isn't an amount, noting what it said; None to give up."""

    masked = low
    for match in _RULING.finditer(masked):
        facts.ruling_mentioned = True
        facts.ruling = facts.ruling or not match.group("neg")
        masked = _blank(masked, *match.span())
    for match in _CONTRIB_PCT.finditer(masked):
        group = "a" if match.group("a") else "b"
        masked = _blank(masked, *match.span(group))
    for pattern in (_CODES, _STANDARD_TAX_CODE):
        for match in pattern.finditer(masked):
            masked = _blank(masked, *match.span())
    if _TAX_CODE_WORDS.search(low):
        for match in _TAX_CODES.finditer(masked):
            masked = _blank(masked, *match.span())
    for match in _HOURS.finditer(masked):
        masked = _blank(masked, *match.span())
        hours = float(match.group("h"))
        weekly = match.group("unit") in (None, "week", "wk") and match.group("abbr") in (None, "pw")
        if facts.hours_per_week is None and not match.group("range") and weekly and 1 <= hours <= 100:
            facts.hours_per_week = hours
    for match in _DATES.finditer(masked):
        masked = _blank(masked, *match.span())

    masked = _mask_children(masked, facts)
    masked = _mask_ages(low, masked, facts)

    for match in _UK_PLAN.finditer(masked):
        masked = _blank(masked, *match.span())
    for match in _YEAR_PREFIXED.finditer(masked):
        prefix = re.sub(r"[\s.]", "", match.group("prefix"))
        kind = {"f": "fy", "a": "ay", "y": "ya"}.get(prefix[0], "tax")
        text = match.group("a")
        first = 2000 + int(text) if len(text) == 2 else int(text)
        facts.years.append((match.start(), kind, first, _second_year(first, match.group("b"))))
        masked = _blank(masked, *match.span())
    for match in _YEAR_RANGE.finditer(masked):
        first = int(match.group("a"))
        second = _second_year(first, match.group("b"))
        if second == first + 1:
            facts.years.append((match.start(), "range", first, second))
            masked = _blank(masked, *match.span())
    for match in _YEAR_SHORT.finditer(masked):
        first, second = int(match.group("a")), int(match.group("b"))
        if second == first + 1 and 15 <= first <= 39:
            facts.years.append((match.start(), "short", 2000 + first, 2000 + second))
            masked = _blank(masked, *match.span())

    if _LEFTOVER_PERCENT.search(masked):
        return None
    return masked


def _mask_children(masked: str, facts: _Facts) -> str:
    total = 0
    counted = False
    for match in _CHILD_COUNT.finditer(masked):
        number = match.group("n")
        total += int(number) if number.isdigit() else _COUNT_WORDS[number]
        masked = _blank(masked, *match.span())
        counted = True
    if not counted:
        for match in _MULTIPLES.finditer(masked):
            total += 2 if match.group() == "twins" else 3
            masked = _blank(masked, *match.span())
            counted = True
    if not counted:
        for match in _MY_CHILD.finditer(masked):
            total += 1
            masked = _blank(masked, *match.span())
            counted = True
    for match in _CHILD_FIELD.finditer(masked):
        total += int(match.group("n"))
        masked = _blank(masked, *match.span())
        counted = True
    if counted:
        facts.children = total
        facts.children_stated = True
    return masked


def _mask_ages(low: str, masked: str, facts: _Facts) -> str:
    for match in _PARENT_AGED.finditer(masked):
        facts.parents_senior = facts.parents_senior or int(match.group("num")) >= 60
        masked = _blank(masked, *match.span())
    for match in _PARENT_SENIOR.finditer(masked):
        facts.parents_senior = True
        masked = _blank(masked, *match.span())
    for match in _PARENT_AGE.finditer(masked):
        number = int(match.group("num"))
        op = match.group("op") or ""
        if not op.startswith(_UNDER) and (number >= 60 or (op and number >= 59)):
            facts.parents_senior = True
        masked = _blank(masked, *match.span())
    for match in _OWN_AGE.finditer(masked):
        start, end = match.span()
        if match.group("lead").startswith(("age", "turning")) and _near_kin(low, start, end):
            masked = _blank(masked, start, end)
            continue
        number = int(match.group("num"))
        age = number - 1 if (match.group("op") or "").startswith(_UNDER) else number
        if 15 <= age <= 120:
            facts.age = age if facts.age is None else facts.age
            masked = _blank(masked, start, end)
    for match in _AGE_SUFFIX.finditer(masked):
        start, end = match.span()
        number = int(match.group("num"))
        if _near_kin(low, start, end):
            masked = _blank(masked, start, end)
        elif 15 <= number <= 120:
            facts.age = number if facts.age is None else facts.age
            masked = _blank(masked, start, end)
    if facts.age is None:
        if _SUPER_SENIOR.search(masked):
            facts.age = 80
        elif _SENIOR.search(masked):
            facts.age = 60
    return masked


_NUMBER = re.compile(
    r"(?:(?<=rs)|(?<=rs\.)|(?<=inr)|(?<=usd)|(?<=gbp)|(?<=eur)|(?<=sgd)|(?<![0-9a-z_.,]))"
    r"(?:\d{1,3}(?: \d{3})+(?!\d)(?:[.,]\d{1,2}(?!\d))?|\d(?:[\d,.]*\d)?)"
)
_WESTERN_GROUPS = re.compile(r"\d{1,3}(?:,\d{3})+")
_INDIAN_GROUPS = re.compile(r"\d{1,2}(?:,\d{2})*,\d{3}")
_DECIMAL_COMMA = re.compile(r"\d+,\d{1,2}")
_DOT_GROUPS = re.compile(r"\d{1,3}(?:\.\d{3})+")
_EURO_CONTEXT = re.compile(r"€|\beur(?:os?)?\b|ireland|irish|netherlands|dutch|holland|\bnl\b")
_CURRENCY_BEFORE = re.compile(
    r"(?<![a-z])(?:(?P<usd>us\$|usd)|(?P<sgd>s\$|sg\$|sgd)"
    r"|(?P<unsupported>c\$|cad|a\$|aud|nz\$|nzd|hk\$|hkd|¥|jpy|chf|aed|rm|myr|kr|r\$|brl|zar)"
    r"|(?P<dollar>\$)|(?P<gbp>£|gbp)|(?P<eur>€|euros?|eur)|(?P<inr>₹|inr|rs\.?|rupees))\s*$"
)
_CURRENCY_AFTER = re.compile(
    r"\s*(?:(?P<unsupported>c\$|cad|a\$|aud|nz\$|nzd|hkd|yen|jpy|chf|aed|dirhams?|ringgit|myr|brl|"
    r"reais|zar|rand|kroner?|kronor|krona|canadian\s+dollars?|australian\s+dollars?)"
    r"|(?P<sgd>sgd|s\$|singapore\s+dollars?)|(?P<usd>usd|us\$|us\s+dollars?)"
    r"|(?P<dollar>dollars?|bucks|\$)|(?P<gbp>gbp|pounds?(?:\s+sterling)?|quid|sterling)"
    r"|(?P<eur>eur|euros?|€)|(?P<inr>inr|rupees?|rs\.?|₹|/-))(?![a-z])"
)
_CURRENCY_GROUPS = ("unsupported", "usd", "sgd", "dollar", "gbp", "eur", "inr")
_MULTIPLIER = re.compile(
    r"\s*(?P<word>thousand|grand|million|mill|mil|mio|billion|bn|lakhs?|lacs?|lpa|crores?|cr)\b"
    r"|(?P<attached>k|mn|m|l)\b|\s+(?P<spaced>k)\b"
)
_MULTIPLIERS: Dict[str, Tuple[float, bool]] = {
    "k": (1e3, False), "thousand": (1e3, False), "grand": (1e3, False),
    "million": (1e6, False), "mill": (1e6, False), "mil": (1e6, False), "mio": (1e6, False),
    "mn": (1e6, False), "m": (1e6, False), "billion": (1e9, False), "bn": (1e9, False),
    "lakh": (1e5, True), "lakhs": (1e5, True), "lac": (1e5, True), "lacs": (1e5, True),
    "l": (1e5, True), "lpa": (1e5, True), "crore": (1e7, True), "crores": (1e7, True),
    "cr": (1e7, True),
}
_PERIOD_AFTER = re.compile(
    r"\s*(?:(?:in\s+)?(?:a|an|per|each|every)\s+|/\s*)"
    r"(?P<unit>year|yr|annum|month|mo|mth|week|wk|hour|hr|day|fortnight)s?\b"
    r"|\s*(?P<adverb>annually|yearly|monthly|weekly|hourly|daily|fortnightly|bi-?weekly|"
    r"semi-?monthly)\b"
    r"|\s*(?P<twice>twice\s+(?:a|per|each|every)\s+month|every\s+(?:two|2|other)\s+weeks?)\b"
    r"|\s*(?P<abbr>p\.?a\.?|pcm|p\.?m\.?|p\.?w\.?|p\.?h\.?|p/m|p/a)(?![a-z])"
)
_PERIOD_BEFORE = re.compile(
    r"\b(?P<adj>monthly|weekly|annual|yearly|hourly|daily|fortnightly|bi-?weekly)"
    r"(?:\s+(?:gross|net|base|basic|take[- ]home|in[- ]hand|total|fixed))?"
    r"(?:\s+(?:salary|pay|income|wages?|ctc|package|earnings|compensation|stipend))?"
    r"\s*(?:(?:of|is|=|:|at|about|around|roughly|approximately)\s*){0,2}$"
    r"|\b(?:salary|pay|income|wages?|earnings|stipend)\s+(?:per|a|an|each)\s+"
    r"(?P<unit>year|annum|month|week|hour|day|fortnight)\s*(?:of|is|=|:)?\s*$"
    r"|\bper\s+(?P<unit2>month|year|week|annum)\s+(?:salary|pay|income)\s*(?:of|is|=|:)?\s*$"
)
_PERIOD_WORDS: Dict[str, str] = {
    "year": "year", "yr": "year", "annum": "year", "annually": "year", "yearly": "year",
    "annual": "year", "pa": "year", "p/a": "year",
    "month": "month", "mo": "month", "mth": "month", "monthly": "month", "pcm": "month",
    "pm": "month", "p/m": "month",
    "week": "week", "wk": "week", "weekly": "week", "pw": "week",
    "hour": "hour", "hr": "hour", "hourly": "hour", "ph": "hour",
    "day": "day", "daily": "day",
    "fortnight": "fortnight", "fortnightly": "fortnight", "biweekly": "fortnight",
    "bi-weekly": "fortnight", "semimonthly": "semimonth", "semi-monthly": "semimonth",
}
_SALARY_LEAD = re.compile(
    r"\b(?:salary|income|earn\w*|pay|paid|wages?|ctc|package|make|making|makes|get|gets|getting)\s*"
    r"(?:(?:is|of|at|about|around|roughly|approx\w*|only|just)\s+|[=:]\s*)?$"
)


def _parse_number(raw: str, euro: bool) -> Optional[float]:
    """Read "1,50,000", "50,000.50", "60.000,50" (and "60.000" for euros) as a number."""

    text = raw.replace(" ", "")
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        whole, _, fraction = text.rpartition(decimal)
        whole = whole.replace("." if decimal == "," else ",", "")
        if not (whole.isdigit() and fraction.isdigit()):
            return None
        return float(whole + "." + fraction)
    if "," in text:
        if _WESTERN_GROUPS.fullmatch(text) or _INDIAN_GROUPS.fullmatch(text):
            return float(text.replace(",", ""))
        if _DECIMAL_COMMA.fullmatch(text):
            return float(text.replace(",", "."))
        digits = text.replace(",", "")
        return float(digits) if digits.isdigit() else None
    if text.count(".") > 1:
        return float(text.replace(".", "")) if _DOT_GROUPS.fullmatch(text) else None
    if "." in text:
        whole, _, fraction = text.partition(".")
        if euro and len(fraction) == 3 and len(whole) <= 3:
            return float(whole + fraction)
    return float(text)


def _unsupported_currency(token: str) -> str:
    token = " ".join(token.split())
    if token in ("c$", "cad") or token.startswith("canadian"):
        return "Canadian dollars"
    if token in ("a$", "aud") or token.startswith("australian"):
        return "Australian dollars"
    names = {
        "nz$": "New Zealand dollars", "nzd": "New Zealand dollars",
        "hk$": "Hong Kong dollars", "hkd": "Hong Kong dollars",
        "¥": "yen", "jpy": "yen", "yen": "yen", "chf": "Swiss francs",
        "aed": "dirhams", "dirham": "dirhams", "dirhams": "dirhams",
        "rm": "ringgit", "myr": "ringgit", "ringgit": "ringgit",
        "r$": "reais", "brl": "reais", "reais": "reais", "zar": "rand", "rand": "rand",
    }
    return names.get(token, "kroner")


def _currency_of(match: "re.Match[str]") -> Optional[str]:
    for name in _CURRENCY_GROUPS:
        token = match.group(name)
        if token:
            return "x:" + _unsupported_currency(token) if name == "unsupported" else name
    return None


def _period_of(match: "re.Match[str]") -> str:
    if match.group("twice"):
        return "semimonth" if match.group("twice").startswith("twice") else "fortnight"
    word = match.group("unit") or match.group("adverb") or match.group("abbr").replace(".", "")
    return _PERIOD_WORDS[word]


def _read_amount(masked: str, number: "re.Match[str]", euro: bool) -> Optional[_Amount]:
    raw = number.group()
    value = _parse_number(raw, euro)
    if value is None:
        return None
    start, cursor = number.span()
    currency: Optional[str] = None
    before = _CURRENCY_BEFORE.search(masked, max(0, start - 16), start)
    if before:
        currency = _currency_of(before)
        start = before.start()
    multiplied = indian = False
    period: Optional[str] = None
    multiplier = _MULTIPLIER.match(masked, cursor)
    if multiplier:
        word = multiplier.group("word") or multiplier.group("attached") or multiplier.group("spaced")
        factor, indian = _MULTIPLIERS[word]
        value *= factor
        multiplied = True
        period = "year" if word == "lpa" else None
        cursor = multiplier.end()
    after = _CURRENCY_AFTER.match(masked, cursor)
    if after:
        stated = _currency_of(after)
        # A bare "$" or "dollars" defers to a more specific currency on the other side.
        currency = stated if currency in (None, "dollar") else currency
        cursor = after.end()
    if period is None:
        found = _PERIOD_AFTER.match(masked, cursor)
        if found and (not found.group("abbr") or currency or multiplied or value >= 100):
            period = _period_of(found)
            cursor = found.end()
    if period is None:
        found = _PERIOD_BEFORE.search(masked, max(0, start - 60), start)
        if found:
            period = _PERIOD_WORDS[found.group("adj") or found.group("unit") or found.group("unit2")]
    if not (currency or multiplied or period or value >= 1000):
        return None
    bare_year = (
        raw.isdigit() and len(raw) == 4 and 1900 <= value <= 2099
        and not (currency or multiplied or period)
        and not _SALARY_LEAD.search(masked[max(0, start - 40):start])
    )
    return _Amount(
        start=start, end=cursor, value=value, raw=raw, currency=currency, period=period,
        implied_inr=indian and currency is None, multiplied=multiplied, bare_year=bare_year,
    )


def _find_amounts(masked: str, low: str) -> List[_Amount]:
    euro = bool(_EURO_CONTEXT.search(low))
    found: List[_Amount] = []
    pos = 0
    while True:
        number = _NUMBER.search(masked, pos)
        if number is None:
            return found
        amount = _read_amount(masked, number, euro)
        if amount is None:
            pos = number.end()
        else:
            found.append(amount)
            pos = amount.end


_SEC = r"(?:(?:u/s|under\s+section|under|section|sec\.?)\s*)?"
_KEYWORDS = re.compile(
    r"(?<![a-z0-9])(?:"
    r"(?P<home_loan_principal>home[\s-]*loan\s+principal(?:\s+repayment)?"
    r"|principal\s+(?:repayment\s+)?(?:on|of)\s+(?:my\s+)?(?:home|housing)\s+loan)"
    r"|(?P<home_loan_interest>(?:home|housing)[\s-]*loan\s+(?:emi\s+)?interest"
    r"|interest\s+(?:paid\s+)?on\s+(?:my\s+|the\s+)?(?:home|housing)\s+loan"
    r"|" + _SEC + r"24\s*\(\s*b\s*\)|section\s+24b?)"
    r"|(?P<home_loan>(?:home|housing)[\s-]*loans?)"
    r"|(?P<nps>" + _SEC + r"80[\s-]?ccd[\s-]*\(?\s*1\s*b\s*\)?|" + _SEC + r"80[\s-]?ccd(?![\s-]*\(?\s*2)"
    r"|nps|national\s+pension\s+(?:system|scheme))"
    r"|(?P<parents>(?:parents?'?s?|mother'?s|father'?s)\s+(?:health|medical)\s+"
    r"(?:insurance|cover|policy|premiums?)"
    r"|(?:health|medical)\s+(?:insurance|cover|policy|premiums?)\s+(?:for|of)\s+(?:my\s+)?parents"
    r"|" + _SEC + r"80\s*d\s+(?:for\s+)?(?:my\s+)?parents|parents?|mother|father|mum|mom|dad|in-?laws?)"
    r"|(?P<self_80d>" + _SEC + r"80[\s-]?d(?![a-z0-9])"
    r"|(?:health|medical)\s+(?:insurance|cover|policy)(?:\s+premiums?)?|mediclaim"
    r"|preventive\s+health\s+check-?up)"
    r"|(?P<s80c>" + _SEC + r"80[\s-]?c(?![a-z0-9])|ppf|elss|epf|vpf|lic|life\s+insurance(?:\s+premiums?)?"
    r"|sukanya(?:\s+samriddhi)?|ssy|nsc|ulip"
    r"|tax[\s-]?sav(?:er|ing)\s+(?:fds?|fixed\s+deposits?|mutual\s+funds?)|tuition\s+fees?)"
    r"|(?P<s80e>" + _SEC + r"80[\s-]?e(?![a-z0-9])|education\s+loan(?:\s+interest)?)"
    r"|(?P<s80g>" + _SEC + r"80[\s-]?g(?![a-z0-9])|donat\w*|charit\w*)"
    r"|(?P<bonus>bonus(?:es)?|incentives?|commissions?|variable\s+pay"
    r"|13th[\s-]month(?:\s+(?:pay|salary|bonus))?|joining\s+bonus|sign[\s-]?on\s+bonus"
    r"|annual\s+wage\s+supplement)"
    r"|(?P<cpf>cpf(?:\s+contributions?)?)"
    r"|(?P<spouse>(?<!ex-)(?<!ex\s)(?:wife|husband|spouse|partner)(?:'s)?"
    r"(?:\s+(?:earns|makes|income|salary|earning|making|pay|wage))?)"
    r"|(?P<pension>pension\s+income|pensions?|401\s*\(?k\)?|403\s*\(?b\)?|457\s*\(?b\)?|ira|roth"
    r"|retirement|superannuation|salary\s+sacrifice|kiwisaver|rrsp)"
    r"|(?P<rent>rental\s+income|rent(?:al)?|hra|house\s+rent\s+allowance)"
    r"|(?P<loan>student\s+loans?|loans?|debts?|emis?|mortgages?)"
    r"|(?P<other>" + _SEC + r"80[\s-]?(?:ddb?|u|tt[ab]|gg[abc]?|ee[ab]?|ccd[\s-]*\(?\s*2\s*\)?|ccc)"
    r"|section\s+10\S*|lta|leave\s+travel\s+allowance|standard\s+deduction|professional\s+tax"
    r"|gratuity|deductions?|exemptions?|allowances?|reimbursements?|perks?|expenses?"
    r"|(?:dividend|interest|capital\s+gains?|investment|savings|side|crypto|other|passive|foreign)"
    r"\s+income|dividends?|capital\s+gains?|rsus?|esops?|stock\s+options?|shares)"
    r"|(?P<salary>salary\s+(?:and|&|\+|plus|incl\w*|with)\s+bonus(?:es)?|salary|salaries|ctc|package"
    r"|income(?![\s-]*tax)|earn(?:s|ed|ing)?|makes?|making|made|wages?|gross|stipend|take[\s-]?home"
    r"|in[\s-]hand|net|compensation|comp|tc|lpa)"
    r")(?![a-z0-9])"
)
_GAP_CHARS = r"[\s:=~()\-]"
_BACK_WORDS = (
    r"of|is|was|are|at|about|around|approx(?:imately|\.)?|roughly|up\s+to|upto|worth|paid|pay|"
    r"i\s+pay|premiums?|investments?|invested|contributions?|contributed|claim(?:ed|s)?|"
    r"deductions?|interest|annual(?:ly)?|yearly|per\s+(?:year|annum)|a\s+year|amount|total|my|our|"
    r"a|an|the|on|for\s+(?:self|myself)|self|by|be|will\s+be|would\s+be|comes\s+to|nearly|almost|"
    r"over|estimated|expected|currently|now|only|just|exactly|limit|max(?:imum)?|full|fully|maxed|"
    r"out|already|completely|exhausted"
)
_FORWARD_WORDS = (
    r"in|into|as|under|u/s|towards?|via|through|for|on|of|to|my|our|the|a|an|paid|invested|spent|"
    r"put|per\s+(?:year|annum)|a\s+year|annually|each|every|year"
)
_BACK_GAP = re.compile(
    r"(?:" + _GAP_CHARS + r"|(?<![a-z])(?:" + _BACK_WORDS + r")(?![a-z]))*"
)
_FORWARD_GAP = re.compile(
    r"(?:" + _GAP_CHARS + r"|(?<![a-z])(?:" + _FORWARD_WORDS + r")(?![a-z]))*"
)
_HEALTH = re.compile(r"80\s*d(?![a-z0-9])|health|medical|mediclaim")
_PROMOTABLE = ("loan", "pension", "rent", "other", "home_loan")


def _find_keywords(low: str, masked: str, amounts: Sequence[_Amount]) -> List[_Keyword]:
    found: List[_Keyword] = []
    for match in _KEYWORDS.finditer(low):
        start, end = match.span()
        if any(amount.start < end and start < amount.end for amount in amounts):
            continue
        # Stretch over blanked neighbours so "parents over 60: 50000" still pairs up.
        while end < len(masked) and masked[end] == "\x00":
            end += 1
        while start > 0 and masked[start - 1] == "\x00":
            start -= 1
        found.append(_Keyword(start, end, match.lastgroup or "other", match.group()))
    return found


def _gap_score(left: object, right: object, masked: str) -> Optional[Tuple[int, int]]:
    """Score pairing two neighbours: (1, 1) for keyword-then-amount, (1, 0) the other way."""

    if isinstance(left, _Keyword) == isinstance(right, _Keyword):
        return None
    gap = masked[left.end:right.start]  # type: ignore[attr-defined]
    if len(gap) > 60:
        return None
    if isinstance(left, _Keyword):
        return (1, 1) if _BACK_GAP.fullmatch(gap) else None
    return (1, 0) if _FORWARD_GAP.fullmatch(gap) else None


def _associate(amounts: List[_Amount], keywords: List[_Keyword], masked: str, low: str) -> None:
    """Give each amount the role of the keyword it belongs to; unpaired amounts are salaries."""

    items: List[object] = sorted([*amounts, *keywords], key=lambda item: item.start)  # type: ignore[attr-defined]
    count = len(items)
    edges = [_gap_score(items[i], items[i + 1], masked) for i in range(count - 1)] + [None]
    best: List[Tuple[int, int]] = [(0, 0)] * (count + 2)
    for i in range(count - 1, -1, -1):
        best[i] = best[i + 1]
        edge = edges[i]
        if edge is not None:
            take = (edge[0] + best[i + 2][0], edge[1] + best[i + 2][1])
            best[i] = max(best[i], take)
    i = 0
    while i < count:
        edge = edges[i]
        if edge is None or (edge[0] + best[i + 2][0], edge[1] + best[i + 2][1]) != best[i]:
            i += 1
            continue
        left, right = items[i], items[i + 1]
        if isinstance(left, _Keyword):
            amount, keyword = right, left
        else:
            amount, keyword = left, right
        assert isinstance(amount, _Amount) and isinstance(keyword, _Keyword)
        amount.role, amount.keyword, amount.paired = keyword.role, keyword.text, True
        if keyword is right:
            amount.paired_forward_ws = not masked[amount.end:keyword.start].strip()
        elif keyword.role == "self_80d" and i + 2 < count:
            following = items[i + 2]
            if (
                isinstance(following, _Keyword) and following.role == "parents"
                and _FORWARD_GAP.fullmatch(masked[amount.end:following.start])
            ):
                amount.role, amount.keyword = "parents", following.text
        i += 2
    for amount in amounts:
        if amount.role == "parents" and not _HEALTH.search(low):
            amount.role = "other"


def _promote(amounts: Sequence[_Amount]) -> Optional[_Amount]:
    """With no plain salary, use a partner's pay or a "50000 pension"-style figure as one."""

    for amount in amounts:
        if amount.role == "spouse" or (amount.role in _PROMOTABLE and amount.paired_forward_ws):
            amount.role = "salary"
            return amount
    return None


# Places: each name maps to a country key, "us:XX" for a state, or "x:Name" for
# somewhere tax-break doesn't cover. The US state names themselves come from
# tax-break (see _place_table).
_PLACE_KINDS: Dict[str, str] = {}


def _register_places(kind: str, names: str) -> None:
    for name in names.split(","):
        name = " ".join(name.split())
        if name:
            _PLACE_KINDS[name] = kind


_register_places("india", """
    india, indian, bharat, mumbai, bombay, delhi, new delhi, bangalore, bengaluru, hyderabad,
    chennai, madras, kolkata, calcutta, pune, ahmedabad, gurgaon, gurugram, noida, jaipur, lucknow,
    kochi, cochin, chandigarh, indore, bhopal, nagpur, surat, vadodara, coimbatore, visakhapatnam,
    vizag, thiruvananthapuram, trivandrum, mysore, mysuru, bhubaneswar, patna, ranchi, guwahati,
    dehradun, nashik, thane, navi mumbai, mangalore, mangaluru, maharashtra, karnataka, tamil nadu,
    kerala, telangana, andhra pradesh, gujarat, rajasthan, uttar pradesh, madhya pradesh,
    west bengal, bihar, odisha, orissa, haryana, assam, jharkhand, uttarakhand, himachal pradesh, goa
""")
_register_places("uk", "uk, u.k., united kingdom, britain, great britain, british")
_register_places("ewni", """
    england, wales, welsh, northern ireland, northern irish, london, manchester, birmingham, leeds,
    liverpool, bristol, sheffield, newcastle, nottingham, leicester, southampton, brighton,
    coventry, cardiff, swansea, belfast, derry, londonderry, milton keynes, kent, essex, sussex,
    yorkshire, lancashire, cornwall, devon, hertfordshire, berkshire, hampshire
""")
_register_places(
    "scotland", "scotland, scottish, edinburgh, glasgow, aberdeen, dundee, inverness, stirling"
)
_register_places("us", """
    usa, u.s., u.s, u.s.a., u.s.a, america, american, united states, united states of america
""")
_register_places("us:DC", "washington dc, washington d.c., d.c., dc, district of columbia")
for _code, _cities in (
    ("NY", "nyc, new york city, manhattan, brooklyn, bronx"),
    ("CA", "los angeles, san francisco, bay area, silicon valley, san diego, san jose, sacramento, "
           "oakland"),
    ("WA", "seattle"), ("IL", "chicago"), ("MA", "boston"),
    ("TX", "austin, dallas, houston, san antonio"), ("FL", "miami, orlando, tampa"),
    ("GA", "atlanta"), ("CO", "denver"), ("AZ", "phoenix"), ("PA", "philadelphia, pittsburgh"),
    ("MI", "detroit"), ("MN", "minneapolis"), ("OR", "portland"), ("NV", "las vegas"),
    ("TN", "nashville"), ("NC", "raleigh"), ("UT", "salt lake city"), ("LA", "new orleans"),
    ("MO", "st. louis, st louis, kansas city"), ("MD", "baltimore"), ("OH", "columbus, cleveland"),
    ("IN", "indianapolis"), ("WI", "milwaukee"), ("HI", "honolulu"), ("AK", "anchorage"),
):
    _register_places("us:" + _code, _cities)
_register_places("ireland", """
    ireland, irish, republic of ireland, eire, éire, dublin, cork, galway, limerick, waterford,
    kilkenny
""")
_register_places("netherlands", """
    netherlands, the netherlands, dutch, holland, nl, amsterdam, rotterdam, the hague, den haag,
    utrecht, eindhoven, groningen, leiden, delft, haarlem
""")
_register_places("singapore", "singapore, singaporean, sg, s'pore")
for _name, _words in (
    ("Canada", "canada, canadian, toronto, vancouver, montreal, ottawa, calgary, ontario, quebec, "
               "alberta, british columbia"),
    ("Australia", "australia, australian, sydney, melbourne, brisbane, perth, adelaide, canberra, "
                  "queensland, new south wales"),
    ("New Zealand", "new zealand, auckland, wellington"),
    ("Germany", "germany, german, berlin, munich, frankfurt, hamburg, deutschland"),
    ("France", "france, french, paris, lyon"),
    ("Spain", "spain, spanish, madrid, barcelona"),
    ("Italy", "italy, italian, rome, milan"),
    ("Portugal", "portugal, portuguese, lisbon"),
    ("Belgium", "belgium, belgian, brussels"),
    ("Switzerland", "switzerland, swiss, zurich, geneva"),
    ("Austria", "austria, austrian, vienna"),
    ("Sweden", "sweden, swedish, stockholm"),
    ("Norway", "norway, norwegian, oslo"),
    ("Denmark", "denmark, danish, copenhagen"),
    ("Finland", "finland, finnish, helsinki"),
    ("Poland", "poland, polish, warsaw"),
    ("Japan", "japan, japanese, tokyo, osaka"),
    ("China", "china, chinese, beijing, shanghai, shenzhen"),
    ("Hong Kong", "hong kong"),
    ("Taiwan", "taiwan, taiwanese, taipei"),
    ("South Korea", "south korea, korea, korean, seoul"),
    ("the UAE", "uae, u.a.e., united arab emirates, dubai, abu dhabi, emirates"),
    ("Saudi Arabia", "saudi arabia, saudi, riyadh, jeddah"),
    ("Qatar", "qatar, doha"),
    ("Malaysia", "malaysia, malaysian, kuala lumpur"),
    ("Indonesia", "indonesia, indonesian, jakarta, bali"),
    ("the Philippines", "philippines, filipino, manila"),
    ("Thailand", "thailand, thai, bangkok"),
    ("Vietnam", "vietnam, vietnamese, hanoi, ho chi minh city, saigon"),
    ("Pakistan", "pakistan, pakistani, karachi, lahore, islamabad"),
    ("Bangladesh", "bangladesh, bangladeshi, dhaka"),
    ("Sri Lanka", "sri lanka, sri lankan, colombo"),
    ("Nepal", "nepal, nepali, nepalese, kathmandu"),
    ("South Africa", "south africa, south african, johannesburg, cape town, durban"),
    ("Nigeria", "nigeria, nigerian, lagos, abuja"),
    ("Kenya", "kenya, kenyan, nairobi"),
    ("Egypt", "egypt, egyptian, cairo"),
    ("Israel", "israel, israeli, tel aviv, jerusalem"),
    ("Turkey", "turkey, turkish, türkiye, istanbul, ankara"),
    ("Russia", "russia, russian, moscow"),
    ("Brazil", "brazil, brazilian, sao paulo, são paulo, rio de janeiro"),
    ("Mexico", "mexico, mexican, mexico city"),
    ("Argentina", "argentina, argentinian, argentine, buenos aires"),
    ("Chile", "chile, chilean, santiago"),
    ("Colombia", "colombia, colombian, bogota, bogotá"),
    ("Luxembourg", "luxembourg"),
    ("Greece", "greece, greek"),
    ("Czechia", "czechia, czech republic, czech, prague"),
    ("Hungary", "hungary, hungarian, budapest"),
    ("Romania", "romania, romanian, bucharest"),
    ("Estonia", "estonia, estonian, tallinn"),
    ("Latvia", "latvia, latvian"),
    ("Lithuania", "lithuania, lithuanian"),
    ("Cyprus", "cyprus, cypriot"),
    ("Malta", "malta, maltese"),
    ("Iceland", "iceland, icelandic"),
    ("Guernsey", "guernsey"),
    ("the Isle of Man", "isle of man, manx"),
    ("Latin America", "latin america, latin american"),
    ("South America", "south america, south american"),
    ("Central America", "central america, central american"),
):
    _register_places("x:" + _name, _words)


@lru_cache(maxsize=4)
def _place_table(
    states: Tuple[Tuple[str, str], ...]
) -> Tuple["re.Pattern[str]", Dict[str, str]]:
    """The place-name pattern and kinds, with ``states`` (code, name) added."""

    kinds = {" ".join(name.lower().split()): "us:" + code for code, name in states}
    kinds.update(_PLACE_KINDS)
    pattern = re.compile(
        r"(?<![a-z])(?:"
        + "|".join(re.escape(name) for name in sorted(kinds, key=len, reverse=True))
        + r")(?![a-z])"
    )
    return pattern, kinds


_US_LOWER = re.compile(
    r"(?<!\bgive\s)(?<!\btell\s)(?<!\bshow\s)(?<!\bhelp\s)(?<!\blet\s)(?<!\bto\s)(?<!\bwith\s)"
    r"\bus\s+(?:federal\s+|income\s+|state\s+)*"
    r"(?:tax(?:es)?|take[- ]?home|salary|income|paycheck|net\s+pay)\b"
    r"|\b(?:in|from|for)\s+the\s+us\b"
)
_US_UPPER = re.compile(r"\bUS\b")
_US_STATE_CODE = re.compile(r"\b(?i:in|from|state\s+of)\s+(?P<code>[A-Z]{2})\b")


def _places(original: str, states: Sequence[Tuple[str, str]] = ()) -> List[Tuple[int, str]]:
    """Every place named in the question, as (position, kind), in order.

    ``states`` are tax-break's US states as (code, name); without them, states
    are found only through the cities and abbreviations Jarvis knows.
    """

    pattern, kinds = _place_table(tuple(states))
    codes = {code for code, _name in states}
    lowered = original.lower()
    found = [(m.start(), kinds[m.group()]) for m in pattern.finditer(lowered)]
    found += [(m.start(), "us") for m in _US_LOWER.finditer(lowered)]
    letters = [c for c in original if c.isalpha()]
    shouting = len(letters) >= 8 and sum(c.isupper() for c in letters) > 0.6 * len(letters)
    if not shouting:
        found += [(m.start(), "us") for m in _US_UPPER.finditer(original)]
        for m in _US_STATE_CODE.finditer(original):
            code = m.group("code")
            if code in codes and code != "LA":
                found.append((m.start("code"), "us:" + code))
    return sorted(found)


def _signal(pattern: str) -> "re.Pattern[str]":
    return re.compile(r"(?<![a-z0-9])(?:" + pattern + r")(?![a-z0-9])")


# Words that point to one country when the question names no place or currency.
_SIGNALS: Dict[str, Tuple["re.Pattern[str]", ...]] = {
    "india": (
        _signal(
            r"lakhs?|lacs?|crores?|lpa|regimes?|nps|itr|hra|ctc|epf|ppf|elss|87a|115\s*bac|cess|"
            r"slabs?|tds|form\s*16|"
            r"80\s?(?:c|d|e|g|u|cc[cd]|ccd\s*\(?\s*1\s*b\s*\)?|dd|ddb|ee|eea|eeb|gg[abc]?|tt[ab])"
        ),
        re.compile(r"(?<![a-z0-9])(?:fy|ay)\s*\d"),
    ),
    "uk": (
        _signal(
            r"national\s+insurance|ni|p60|p45|personal\s+allowance|student\s+loan\s+plan|"
            r"tax\s+code|1257\s?l|hmrc"
        ),
        _UK_PLAN,
    ),
    "us": (
        _signal(
            r"irs|federal|fica|medicare|social\s+security|401\s*\(?k\)?|403\s*\(?b\)?|w-?2|"
            r"filing\s+status|jointly|separately|head\s+of\s+household|state\s+tax|form\s+1040|"
            r"paycheck"
        ),
    ),
    "ireland": (_signal(r"usc|prsi"),),
    "netherlands": (
        _signal(r"ruling|box\s*1|vakantiegeld|aow|belastingdienst|holiday\s+allowance"),
    ),
    "singapore": (_signal(r"cpf|iras"), re.compile(r"(?<![a-z0-9])ya\s*\d")),
}


def _signals(low: str) -> Dict[str, int]:
    return {
        country: sum(len(pattern.findall(low)) for pattern in patterns)
        for country, patterns in _SIGNALS.items()
    }


def _country_of(kind: str) -> Optional[str]:
    if kind in ("uk", "ewni", "scotland"):
        return "uk"
    if kind == "us" or kind.startswith("us:"):
        return "us"
    return None if kind.startswith("x:") else kind


def _currency_key(amount: _Amount) -> Optional[str]:
    return amount.currency or ("inr" if amount.implied_inr else None)


def _or_list(items: Sequence[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]


_PERIOD_SUFFIX: Dict[str, str] = {
    "month": " a month", "week": " a week", "hour": " an hour", "day": " a day",
    "fortnight": " a fortnight", "semimonth": " twice a month",
}


def _describe(amount: _Amount, symbol: Optional[str] = None) -> str:
    """An amount as the question gave it, e.g. "£3,000 a month" or "50,000"."""

    if symbol:
        text = _money(amount.value, symbol)
    else:
        text = f"{amount.value:,.2f}".rstrip("0").rstrip(".")
    return text + _PERIOD_SUFFIX.get(amount.period or "", "")


def _ask(lines: Sequence[str]) -> _Reply:
    return _Reply(_finish(lines, disclaimer=False))


def _decide(
    places: Sequence[Tuple[int, str]], amounts: Sequence[_Amount], salary: Optional[_Amount],
    low: str,
) -> Tuple[Optional[str], List[str]]:
    """Pick the country, or raise a reply that declines or asks which one."""

    supported: List[str] = []
    for _, kind in places:
        country = _country_of(kind)
        if country and country not in supported:
            supported.append(country)
    currency = _currency_key(salary) if salary else None
    if currency is None:
        currency = next((key for key in map(_currency_key, amounts) if key), None)
    if len(supported) == 1:
        return supported[0], []
    if supported:
        chosen = _CURRENCY_COUNTRY.get(currency or "")
        if chosen in supported:
            return chosen, []
        euro = [c for c in supported if c in ("ireland", "netherlands")]
        if currency == "eur" and len(euro) == 1:
            return euro[0], []
        if salary is None:
            return None, []
        raise _ask([
            f"Which country should I use: {_or_list([_COUNTRY_NAMES[c] for c in supported])}?",
            f'Ask again with one country, e.g. "{_EXAMPLES[supported[0]]}".',
        ])
    unsupported = [kind[2:] for _, kind in places if kind.startswith("x:")]
    if unsupported:
        raise _ask([
            f"With tax-break I cover {_COVERAGE}, so I can't estimate tax for {unsupported[0]}.",
        ])
    foreign = [a.currency[2:] for a in amounts if a.currency and a.currency.startswith("x:")]
    if foreign:
        raise _ask([
            f"With tax-break I cover {_COVERAGE}, so I can't estimate tax on a salary in "
            f"{foreign[0]}.",
        ])
    if currency in _CURRENCY_COUNTRY:
        return _CURRENCY_COUNTRY[currency], []
    signals = _signals(low)
    if currency == "eur":
        euro = [c for c in ("ireland", "netherlands") if signals[c] > 0]
        if len(euro) == 1:
            return euro[0], []
        if salary is None:
            return None, []
        shown = _describe(salary, "€")
        raise _ask([
            f"Which country is the salary of {shown} for: Ireland or the Netherlands?",
            f'Ask e.g. "Irish tax on {shown}" or "Dutch tax on {shown}".',
        ])
    if currency == "dollar":
        if signals["singapore"] > signals["us"]:
            return "singapore", []
        return "us", ["I took $ as US dollars."]
    top = max(signals.values())
    tied = [c for c, count in signals.items() if count == top]
    if top > 0 and len(tied) == 1:
        return tied[0], []
    if salary is None:
        return None, []
    if top > 0:
        raise _ask([
            f"Which country should I use: {_or_list([_COUNTRY_NAMES[c] for c in tied])}?",
            f'Ask again with one country, e.g. "{_EXAMPLES[tied[0]]}".',
        ])
    shown = _describe(salary)
    raise _ask([
        f"Which country is the salary of {shown} for? With tax-break I cover {_COVERAGE}.",
        f'Ask e.g. "UK tax on {shown}" or "tax on {shown} in India".',
    ])


def _check_currencies(country: str, amounts: Sequence[_Amount], notes: List[str]) -> None:
    """Refuse amounts in another country's currency; I don't convert."""

    local = _LOCAL_CURRENCY[country]
    for amount in amounts:
        currency = amount.currency
        if currency is None or currency in _ACCEPTED_CURRENCIES[country]:
            continue
        if currency.startswith("x:"):
            shown, theirs = _describe(amount), currency[2:]
        else:
            shown = _describe(amount, _CURRENCY_SYMBOLS[currency])
            theirs = _CURRENCY_NAMES[currency]
        raise _ask([
            f"{_COUNTRY_ADJECTIVES[country]} tax is worked out in {local}, but {shown} is in "
            f"{theirs}. Give amounts in {local}; I don't convert currencies.",
        ])
    if country == "singapore" and any(a.currency == "dollar" for a in amounts):
        notes.append("I took $ as Singapore dollars.")


def _salary_per_year(
    salary: _Amount, facts: _Facts, symbol: str, notes: List[str]
) -> Tuple[float, float, str]:
    """Return the yearly salary, the figure as stated, and the period it was stated for."""

    period = salary.period or "year"
    value = salary.value
    shown = _describe(salary, symbol)
    if period == "hour":
        hours = facts.hours_per_week
        if hours is None:
            example = f"{_money(value, symbol)} an hour for 40 hours a week"
            raise _ask([
                f"I work from a yearly salary, so I need more than {shown}. Give the "
                f'hours you work a week, e.g. "{example}", or a yearly, monthly or weekly salary.',
            ])
        annual = value * hours * 52
        notes.append(f"I took {shown} for {hours:g} hours a week as {_money(annual, symbol)} a year.")
        return annual, annual, "year"
    if period == "day":
        raise _ask([
            "I work from a yearly salary; give a yearly, monthly or weekly figure rather "
            f"than {shown}.",
        ])
    if period in ("fortnight", "semimonth"):
        annual = value * (26 if period == "fortnight" else 24)
        notes.append(f"I took {shown} as {_money(annual, symbol)} a year.")
        return annual, annual, "year"
    return value * {"year": 1, "month": 12, "week": 52}[period], value, period


def _no_salary(amounts: Sequence[_Amount], country: Optional[str]) -> str:
    found = []
    for amount in amounts:
        symbol = _SYMBOLS.get(country or "") or _CURRENCY_SYMBOLS.get(_currency_key(amount) or "")
        found.append(f'{_describe(amount, symbol)} for "{amount.keyword}"')
    example = _EXAMPLES.get(country or "", _EXAMPLES["uk"])
    return _finish(
        [
            f"I need a gross salary to estimate the tax; I only found {', '.join(found)}.",
            f'Give your gross yearly salary too, e.g. "{example}".',
        ],
        disclaimer=False,
    )


def _india_year(kind: str, first: int, second: Optional[int]) -> Tuple[str, Optional[str]]:
    """Read one year mention as an Indian financial year key and a note on how it was read."""

    if second is not None:
        if second != first + 1:
            return f"FY{first}-{second}", None
        start = first - 1 if kind in ("ay", "ya") else first
        return f"FY{start}-{(start + 1) % 100:02d}", None
    if kind == "fy":
        start = first - 1
        note = f"I took FY {first} as FY {start}-{first % 100:02d} (April {start} to March {first})."
    elif kind in ("ay", "ya"):
        start = first - 1
        note = (
            f"I took AY {first} as AY {first}-{(first + 1) % 100:02d}, for income in "
            f"FY {start}-{first % 100:02d}."
        )
    else:
        start = first
        note = (
            f"I took {first} as FY {first}-{(first + 1) % 100:02d} "
            f"(April {first} to March {first + 1})."
        )
    return f"FY{start}-{(start + 1) % 100:02d}", note


def _asked_year_note(country: str, kind: str, first: int, second: Optional[int]) -> str:
    """Say that tax-break's calculators outside India don't take a year."""

    if second is None:
        span = str(first)
    else:
        span = f"{first}{'/' if country == 'uk' else '-'}{second % 100:02d}"
    asked = {"fy": "FY ", "ay": "AY ", "ya": "YA "}.get(kind, "") + span
    return (
        f"You asked about {asked}, but tax-break's calculator for {_COUNTRY_NAMES[country]} "
        f"doesn't take a year, so this is for the year it's built for, which may not be {asked}."
    )


def _resolve_year(
    country: str, facts: _Facts, meta: _Meta
) -> Tuple[Optional[str], bool, List[str]]:
    """Return the India year key (None elsewhere), whether it was defaulted, and notes."""

    if not facts.years:
        return (meta.latest_year if country == "india" else None), True, []
    years = sorted(facts.years)
    if country != "india":
        return None, False, [_asked_year_note(country, *years[0][1:])]
    key, note = _india_year(*years[0][1:])
    if key not in dict(meta.years):
        raise _Reply(_year_decline(meta, _fy(key)))
    notes = [note] if note else []
    if any(_india_year(*year[1:])[0] != key for year in years[1:]):
        notes.append(f"I used {meta.year_label(key)}, the first year given.")
    return key, False, notes


_BOTH_REGIMES = re.compile(
    r"\b(?:old\s+(?:and|vs\.?|versus|or|v)\s+new|new\s+(?:and|vs\.?|versus|or|v)\s+old|compar\w*|"
    r"which\s+regime|both\s+regimes|better\s+regime|regimes)\b"
)
_OLD_REGIME = re.compile(
    r"\bold\s+(?:tax\s+)?(?:regime|scheme|system|slabs?)\b|\bregime\s*[:=-]?\s*old\b"
)
_NEW_REGIME = re.compile(
    r"\b(?:new|default)\s+(?:tax\s+)?(?:regime|scheme|system|slabs?)\b"
    r"|\bregime\s*[:=-]?\s*new\b|\b115\s*bac\b"
)


def _regime(low: str) -> Optional[str]:
    if _BOTH_REGIMES.search(low):
        return None
    old, new = bool(_OLD_REGIME.search(low)), bool(_NEW_REGIME.search(low))
    if old != new:
        return "old" if old else "new"
    return None


_MAX_KEYS = (
    r"nps|80\s*ccd\s*\(?\s*1\s*b\s*\)?|80\s*c(?![a-z0-9])|ppf|elss|80\s*d(?![a-z0-9])|"
    r"home\s+loan(?:\s+interest)?|housing\s+loan(?:\s+interest)?|24\s*\(\s*b\s*\)"
)
_MAX_KEY = re.compile(_MAX_KEYS)
# One key or a list of them: "80c", "80c and nps", "80c, 80d & nps".
_MAX_LIST = (
    r"(?:" + _MAX_KEYS + r")(?:\s*(?:,|&|\+|/|\band\b)\s*(?:section\s+)?(?:" + _MAX_KEYS + r"))*"
)
_MAX_CLAIM = re.compile(
    r"\b(?:full|fully\s+used|max|maximum|maxed(?:\s+out)?|maxing\s+out|entire|whole|complete)\s+"
    r"(?:(?:of\s+)?(?:my|the)\s+)?(?:section\s+)?(?P<key>" + _MAX_LIST + r")"
    r"|(?<![a-z0-9])(?P<key2>" + _MAX_LIST + r")\s+(?:(?:is|are|fully|already|completely)\s+){0,2}"
    r"(?:maxed(?:\s+out)?|max(?:imum)?|full(?:y\s+used)?|limit|exhausted)\b"
)
_INDIA_ROLES: Dict[str, str] = {
    "home_loan_principal": "section_80c", "home_loan_interest": "home_loan_interest",
    "nps": "section_80ccd1b", "parents": "section_80d_parents", "self_80d": "section_80d_self",
    "s80c": "section_80c", "s80e": "section_80e", "s80g": "section_80g",
}
_PER_YEAR: Dict[str, int] = {"year": 1, "month": 12, "week": 52, "fortnight": 26, "semimonth": 24}


def _max_key(text: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", text)
    if key.startswith(("nps", "80ccd")):
        return "section_80ccd1b"
    if key.startswith(("80c", "ppf", "elss")):
        return "section_80c"
    if key.startswith("80d"):
        return "section_80d_self"
    return "home_loan_interest"


def _apply_roles(
    req: _Request, country: str, amounts: Sequence[_Amount], symbol: str, notes: List[str]
) -> None:
    """Fold bonuses, CPF and Indian deductions into the request; note what was left out."""

    for amount in amounts:
        role, keyword = amount.role, amount.keyword
        if role == "salary":
            continue
        shown = _describe(amount, symbol)
        factor = _PER_YEAR.get(amount.period or "year")
        if factor is None:
            notes.append(f'I left out the {shown} for "{keyword}".')
            continue
        yearly = amount.value * factor
        if role in _INDIA_ROLES:
            if country == "india":
                key = _INDIA_ROLES[role]
                req.deductions[key] = req.deductions.get(key, 0.0) + yearly
            else:
                notes.append(f"I left out the {shown} for \"{keyword}\"; it's an Indian deduction.")
        elif role == "bonus":
            req.bonus += yearly
        elif role == "cpf":
            if country == "singapore":
                req.cpf += yearly
            else:
                notes.append(f"I left out the {shown} for \"{keyword}\"; CPF is Singapore's.")
        elif role == "spouse":
            note = f"I left out the {shown} for your spouse or partner; this estimate is for one salary."
            if country == "us":
                note += " For a joint return, give your combined salary."
            notes.append(note)
        elif role == "pension":
            notes.append(f"I left out the {shown} pension amount.")
        elif role == "rent":
            if country == "india" and _HRA.search(keyword):
                notes.append(f"I left out the {shown} of HRA.")
            else:
                notes.append(
                    f"I left out the {shown} for \"{keyword}\"; rent and rental income aren't covered."
                )
        elif role == "loan" and "student" in keyword:
            notes.append(
                f"I left out the {shown} student loan balance; repayments depend on the plan and "
                "salary, not the balance."
            )
        elif role == "home_loan" and country == "india":
            notes.append(
                f"I left out the {shown} for \"{keyword}\"; say whether it's interest (24(b)), e.g. "
                '"home loan interest 1.8 lakh", or principal (80C).'
            )
        else:
            hint = ""
            if country == "india" and keyword in ("deduction", "deductions"):
                hint = '; name the section, e.g. "80C 1 lakh"'
            notes.append(f'I left out the {shown} for "{keyword}"{hint}.')


def _apply_max_claims(req: _Request, country: str, low: str, notes: List[str]) -> None:
    """Claim the full limit for "max 80C"-style phrases that don't give an amount."""

    for match in _MAX_CLAIM.finditer(low):
        text = match.group("key") or match.group("key2")
        keys = [key.group() for key in _MAX_KEY.finditer(text)]
        if country != "india":
            what = "it's an Indian deduction" if len(keys) == 1 else "they're Indian deductions"
            notes.append(f"I left out \"{text}\"; {what}.")
            continue
        for key in map(_max_key, keys):
            if key not in req.deductions:
                req.deductions[key] = math.inf


def _estimate(text: str) -> Optional[str]:
    original, low = _clean(text)
    if not _has_intent(low):
        return None
    gate = _gate(low)
    if gate == "skip":
        return None
    if gate:
        return gate
    facts = _Facts()
    masked = _mask(low, facts)
    if masked is None:
        return None
    amounts = _find_amounts(masked, low)
    # A year on its own ("tax 2025") isn't a salary; alongside one it picks the tax year.
    if all(amount.bare_year for amount in amounts):
        return None
    for amount in amounts:
        if amount.bare_year:
            facts.years.append((amount.start, "bare", int(amount.value), None))
            masked = _blank(masked, amount.start, amount.end)
    amounts = [amount for amount in amounts if not amount.bare_year]
    if any(not math.isfinite(a.value) or a.value > _MAX_INCOME for a in amounts):
        return None

    keywords = _find_keywords(low, masked, amounts)
    _associate(amounts, keywords, masked, low)
    salaries = [amount for amount in amounts if amount.role == "salary"]
    if not salaries:
        promoted = _promote(amounts)
        salaries = [promoted] if promoted else []
    salary = salaries[0] if salaries else None
    # Only a salary needs tax-break; its US state names help find the place.
    meta = _meta() if salary is not None else None
    places = _places(original, meta.states if meta else ())

    try:
        country, notes = _decide(places, amounts, salary, low)
        if salary is None:
            return _no_salary(amounts, country)
        if country is None or meta is None:
            return None
        symbol = _SYMBOLS[country]
        _check_currencies(country, amounts, notes)

        kinds = [kind for _, kind in places]
        scotland = False
        if country == "uk" and "scotland" in kinds:
            if "ewni" in kinds:
                notes.append(
                    "I can't do Scottish income tax with tax-break, so I used the rates for "
                    "England, Wales and Northern Ireland."
                )
            else:
                scotland = True
        state: Optional[str] = None
        if country == "us":
            named = list(dict.fromkeys(kind[3:] for kind in kinds if kind.startswith("us:")))
            codes = [code for code in named if code in dict(meta.states)]
            if codes:
                state = codes[0]
                if len(codes) > 1:
                    notes.append(
                        f"I used {meta.state_name(state)} for state tax, the first state given."
                    )
            elif named:
                notes.append(
                    "tax-break has no state tax figures for the place you named, so I left state "
                    "tax out."
                )

        annual, stated, period = _salary_per_year(salary, facts, symbol, notes)
        if len(salaries) > 1:
            others = " or ".join(_describe(other, symbol) for other in salaries[1:])
            notes.append(
                f"I used {_describe(salary, symbol)}, the first salary given; ask again for {others}."
            )
        fy, defaulted, year_notes = _resolve_year(country, facts, meta)
        notes.extend(year_notes)

        req = _Request(
            text=low, salary=annual, stated=stated, period=period,
            parents_senior=facts.parents_senior,
            regime=_regime(low) if country == "india" else None, age=facts.age,
            children=facts.children, children_stated=facts.children_stated,
            ruling=facts.ruling and country == "netherlands",
        )
        _apply_roles(req, country, amounts, symbol, notes)
        _apply_max_claims(req, country, low, notes)
        if not (0 < req.income <= _MAX_INCOME):
            return None
        if country == "us" and _IE_SINGLE_PARENT.search(low) and _us_status(low)[0] == "single":
            notes.append(
                "As a single parent you may be able to file as head of household; add "
                '"head of household" to use it.'
            )
        if facts.ruling and country != "netherlands":
            notes.append("The 30% ruling is Dutch, so I left it out.")

        if country == "india":
            return _india_reply(req, meta, fy or meta.latest_year, defaulted, notes)
        if country == "uk":
            return _scotland_reply(req) if scotland else _uk_reply(req, meta, notes)
        if country == "us":
            return _us_reply(req, meta, state, notes)
        if country == "ireland":
            return _ireland_reply(req, meta, notes)
        if country == "netherlands":
            return _netherlands_reply(req, meta, notes)
        return _singapore_reply(req, meta, notes)
    except _Reply as reply:
        return reply.reply


def estimate(text: str) -> Optional[str]:
    """Answer a salary tax question with tax-break's engine, or None if it isn't one.

    Raises :class:`jarvis.projects.ProjectUnavailable` when the project or
    Node.js is missing, and :class:`jarvis.projects.ProjectError` when the
    engine fails or answers in an unexpected shape.
    """

    if not text or len(text) > _MAX_TEXT:
        return None
    try:
        return _estimate(text)
    except (ArithmeticError, ValueError):
        return None


def usage() -> str:
    examples = "; ".join(f'"{example}"' for example in _EXAMPLES.values())
    return _finish([
        "I can estimate income tax and take-home pay on a salary with tax-break's tax engine.",
        f"It covers {_COVERAGE}.",
        f"Try: {examples}.",
        'Add details such as "a month", a bonus, "old regime", a financial year for India, '
        '"80C 1 lakh", "student loan plan 2", "married with 2 kids", a US state or "30% ruling".',
    ])
