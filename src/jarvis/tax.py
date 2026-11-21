"""Salary income-tax estimates ported from charles2ke's tax-break engine.

tax-break is charles2ke's zero-dependency TypeScript tax engine (repository
https://github.com/charles2ke/tax-break, live app
https://charles2ke.github.io/tax-break/). This module is a stdlib-only port
of its salary paths at commit a3d630c7eb45d188ffb28da7507df948ca8be59b:

- India, FY 2021-22 to FY 2025-26, old and new regimes:
  packages/tax-engine/src/calculators/slabTax.ts, rebate.ts, surcharge.ts,
  deductions.ts, houseProperty.ts, regime.ts and compare.ts, with the tables
  in packages/tax-engine/src/config/fy2021-22.ts to fy2025-26.ts.
- United Kingdom 2025/26, United States 2025 (federal tax, FICA and the 50
  states plus DC), Ireland 2025, the Netherlands 2025 and Singapore YA 2025:
  calculators/uk.ts, us.ts, usState.ts, ireland.ts, netherlands.ts,
  singapore.ts and international.ts.

The formulas, thresholds, caps and order of operations are the engine's, and
JavaScript's ``Math.round`` is reproduced exactly, so the figures match
tax-break to the cent. Only employment income is covered: tax-break's
document parsers, ITR JSON export and form recommender, HRA, rental income,
capital gains, advance tax and investment income are not ported.

Licence: the tax-break repository ships the AGPL-3.0 licence text, while its
package.json files (the tax engine's included) declare MIT without naming a
copyright holder. Jarvis follows the LICENSE file; see THIRD_PARTY_NOTICES.md.

:func:`estimate` reads a free-text request such as "income tax on 15 lakh in
India" and answers in plain text. The calculators (:func:`india_tax`,
:func:`uk_tax`, :func:`us_tax`, :func:`ireland_tax`, :func:`netherlands_tax`
and :func:`singapore_tax`) are pure functions returning frozen dataclasses.
The tables are the latest that tax-break encodes, not necessarily the
current tax year, and every reply names the year it used. Nothing here is
tax advice.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

PROJECT = "tax-break"
SITE_URL = "https://charles2ke.github.io/tax-break/"
REPO_URL = "https://github.com/charles2ke/tax-break"
SOURCE_COMMIT = "a3d630c7eb45d188ffb28da7507df948ca8be59b"
CREDIT = f"From {PROJECT}: {SITE_URL}"
DISCLAIMER = (
    "This is an estimate for general education, not tax advice — check with "
    "the tax authority or a qualified adviser."
)


# --------------------------------------------------------------------------
# Shared arithmetic
# --------------------------------------------------------------------------

def _js_round(value: float) -> float:
    """Round like JavaScript's ``Math.round``: halves go up, towards +infinity."""

    whole = math.floor(value)
    return float(whole + 1) if value - whole >= 0.5 else float(whole)


def _round2(value: float) -> float:
    """Round to cents exactly as tax-break's ``round2`` helper does."""

    return _js_round(value * 100) / 100


@dataclass(frozen=True)
class Bracket:
    """One tax band: ``rate`` applies to income from ``lower`` up to ``upper``."""

    lower: float
    upper: Optional[float]
    rate: float


def _bands(*points: Tuple[float, float]) -> Tuple[Bracket, ...]:
    """Build contiguous brackets from ``(start, rate)`` pairs; the last is open."""

    brackets = []
    for index, (lower, rate) in enumerate(points):
        upper = float(points[index + 1][0]) if index + 1 < len(points) else None
        brackets.append(Bracket(float(lower), upper, float(rate)))
    return tuple(brackets)


def slab_tax(income: float, slabs: Sequence[Bracket]) -> float:
    """Return progressive tax on ``income`` (tax-break's ``calculateSlabTax``)."""

    income = max(0.0, income)
    tax = 0.0
    for bracket in slabs:
        if income <= bracket.lower:
            break
        upper = income if bracket.upper is None else min(income, bracket.upper)
        tax += max(0.0, upper - bracket.lower) * bracket.rate
    return tax


# --------------------------------------------------------------------------
# India: config/fy2021-22.ts to fy2025-26.ts and the India calculators
# --------------------------------------------------------------------------

INDIA_AGE_BANDS: Tuple[str, ...] = ("below60", "60to80", "above80")
INDIA_REGIMES: Tuple[str, ...] = ("new", "old")

SECTION_80C_CAP = 150000.0
SECTION_80CCD1B_CAP = 50000.0
SECTION_80D_CAP = 25000.0
SECTION_80D_SENIOR_CAP = 50000.0
HOME_LOAN_INTEREST_CAP = 200000.0
HOUSE_PROPERTY_LOSS_CAP = 200000.0


@dataclass(frozen=True)
class IndiaRegimeRules:
    """Slabs by age band, standard deduction, 87A rebate and surcharge tiers."""

    below60: Tuple[Bracket, ...]
    senior: Tuple[Bracket, ...]
    super_senior: Tuple[Bracket, ...]
    standard_deduction: float
    rebate_limit: float
    rebate_max: float
    rebate_marginal_relief: bool
    surcharge_tiers: Tuple[Tuple[float, float], ...]
    cess_rate: float = 0.04

    def slabs(self, age_band: str = "below60") -> Tuple[Bracket, ...]:
        """Return the slabs for ``below60``, ``60to80`` or ``above80``."""

        if age_band == "below60":
            return self.below60
        if age_band == "60to80":
            return self.senior
        if age_band == "above80":
            return self.super_senior
        raise ValueError(f"Unknown age band {age_band!r}; use one of {INDIA_AGE_BANDS}.")


@dataclass(frozen=True)
class IndiaYear:
    """One financial year's rules for the old and new regimes."""

    key: str
    label: str
    old: IndiaRegimeRules
    new: IndiaRegimeRules

    def rules(self, regime: str) -> IndiaRegimeRules:
        if regime == "old":
            return self.old
        if regime == "new":
            return self.new
        raise ValueError(f"Unknown regime {regime!r}; use 'old' or 'new'.")


_SURCHARGE_TO_37 = ((5000000.0, 0.1), (10000000.0, 0.15), (20000000.0, 0.25), (50000000.0, 0.37))
_SURCHARGE_TO_25 = ((5000000.0, 0.1), (10000000.0, 0.15), (20000000.0, 0.25))

_OLD_REGIME = IndiaRegimeRules(
    below60=_bands((0, 0), (250000, 0.05), (500000, 0.2), (1000000, 0.3)),
    senior=_bands((0, 0), (300000, 0.05), (500000, 0.2), (1000000, 0.3)),
    super_senior=_bands((0, 0), (500000, 0.2), (1000000, 0.3)),
    standard_deduction=50000.0,
    rebate_limit=500000.0,
    rebate_max=12500.0,
    rebate_marginal_relief=False,
    surcharge_tiers=_SURCHARGE_TO_37,
)


def _new_regime(
    slabs: Tuple[Bracket, ...],
    standard_deduction: float,
    rebate_limit: float,
    rebate_max: float,
    marginal_relief: bool,
    surcharge_tiers: Tuple[Tuple[float, float], ...],
) -> IndiaRegimeRules:
    return IndiaRegimeRules(
        slabs, slabs, slabs, standard_deduction, rebate_limit, rebate_max,
        marginal_relief, surcharge_tiers,
    )


_NEW_SLABS_2020 = _bands(
    (0, 0), (250000, 0.05), (500000, 0.1), (750000, 0.15), (1000000, 0.2),
    (1250000, 0.25), (1500000, 0.3),
)
_NEW_SLABS_2023 = _bands(
    (0, 0), (300000, 0.05), (600000, 0.1), (900000, 0.15), (1200000, 0.2), (1500000, 0.3),
)
_NEW_SLABS_2025 = _bands(
    (0, 0), (400000, 0.05), (800000, 0.1), (1200000, 0.15), (1600000, 0.2),
    (2000000, 0.25), (2400000, 0.3),
)

INDIA_YEARS: Dict[str, IndiaYear] = {
    "FY2021-22": IndiaYear(
        "FY2021-22", "FY 2021-22 (AY 2022-23)", _OLD_REGIME,
        _new_regime(_NEW_SLABS_2020, 0.0, 500000.0, 12500.0, False, _SURCHARGE_TO_37),
    ),
    "FY2022-23": IndiaYear(
        "FY2022-23", "FY 2022-23 (AY 2023-24)", _OLD_REGIME,
        _new_regime(_NEW_SLABS_2020, 0.0, 500000.0, 12500.0, False, _SURCHARGE_TO_37),
    ),
    "FY2023-24": IndiaYear(
        "FY2023-24", "FY 2023-24 (AY 2024-25)", _OLD_REGIME,
        _new_regime(_NEW_SLABS_2023, 50000.0, 700000.0, 25000.0, True, _SURCHARGE_TO_25),
    ),
    "FY2024-25": IndiaYear(
        "FY2024-25", "FY 2024-25 (AY 2025-26)", _OLD_REGIME,
        _new_regime(_NEW_SLABS_2023, 75000.0, 700000.0, 25000.0, True, _SURCHARGE_TO_25),
    ),
    "FY2025-26": IndiaYear(
        "FY2025-26", "FY 2025-26 (AY 2026-27)", _OLD_REGIME,
        _new_regime(_NEW_SLABS_2025, 75000.0, 1200000.0, 60000.0, True, _SURCHARGE_TO_25),
    ),
}
LATEST_INDIA_FY = "FY2025-26"


@dataclass(frozen=True)
class IndiaDeductions:
    """Old-regime claims as stated; tax-break's caps are applied in :func:`india_tax`.

    ``math.inf`` means "the maximum allowed".
    """

    section_80c: float = 0.0
    section_80d_self: float = 0.0
    section_80d_parents: float = 0.0
    parents_senior: bool = False
    section_80ccd1b: float = 0.0
    section_80e: float = 0.0
    section_80g: float = 0.0
    home_loan_interest: float = 0.0

    def claimed(self) -> bool:
        """Return True if any deduction amount is positive."""

        return any(
            amount > 0
            for amount in (
                self.section_80c, self.section_80d_self, self.section_80d_parents,
                self.section_80ccd1b, self.section_80e, self.section_80g,
                self.home_loan_interest,
            )
        )


@dataclass(frozen=True)
class Surcharge:
    """Surcharge after marginal relief, the relief given and the tier's rate."""

    amount: float
    marginal_relief: float
    rate: float


@dataclass(frozen=True)
class IndiaTax:
    """One regime's computation for a resident individual with salary income."""

    fy: str
    label: str
    regime: str
    age_band: str
    salary: float
    house_property: float
    gross_total_income: float
    standard_deduction: float
    section_80c: float
    section_80d: float
    section_80ccd1b: float
    section_80e: float
    section_80g: float
    total_deductions: float
    taxable_income: float
    tax_before_rebate: float
    rebate: float
    tax_after_rebate: float
    surcharge: float
    surcharge_rate: float
    marginal_relief: float
    cess: float
    unrounded_total: float
    total: float
    effective_rate: float


@dataclass(frozen=True)
class IndiaComparison:
    """Both regimes side by side, as tax-break's ``compareRegimes`` reports them."""

    old: IndiaTax
    new: IndiaTax
    recommended: str
    savings: float


def india_year(fy: str = LATEST_INDIA_FY) -> IndiaYear:
    """Return the rules for ``fy`` ("FY2025-26", "FY 2025-26" or "2025-26")."""

    key = re.sub(r"\s+", "", str(fy)).upper()
    if not key.startswith("FY"):
        key = "FY" + key
    if key not in INDIA_YEARS:
        supported = ", ".join(INDIA_YEARS)
        raise ValueError(f"tax-break has no India table for {fy!r}; use one of {supported}.")
    return INDIA_YEARS[key]


def india_age_band(age: Optional[int]) -> str:
    """Map an age to tax-break's band: below 60, 60 to 79, or 80 and over."""

    if age is None or age < 60:
        return "below60"
    return "60to80" if age < 80 else "above80"


def rebate_87a(taxable_income: float, tax_before_rebate: float, rules: IndiaRegimeRules) -> float:
    """Rebate u/s 87A, with marginal relief where the regime allows it."""

    if taxable_income <= rules.rebate_limit:
        return min(tax_before_rebate, rules.rebate_max)
    if not rules.rebate_marginal_relief:
        return 0.0
    return max(0.0, tax_before_rebate - (taxable_income - rules.rebate_limit))


def india_surcharge(
    taxable_income: float,
    tax_before_surcharge: float,
    tiers: Sequence[Tuple[float, float]],
    slabs: Sequence[Bracket],
) -> Surcharge:
    """Surcharge with marginal relief (tax-break's ``calculateSurcharge``)."""

    ordered = sorted(tiers)
    index = -1
    for position, (threshold, _rate) in enumerate(ordered):
        if taxable_income > threshold:
            index = position
    if index == -1:
        return Surcharge(0.0, 0.0, 0.0)
    threshold, rate = ordered[index]
    previous_rate = ordered[index - 1][1] if index > 0 else 0.0
    raw = tax_before_surcharge * rate
    max_allowed = slab_tax(threshold, slabs) * (1 + previous_rate) + (taxable_income - threshold)
    if tax_before_surcharge + raw > max_allowed:
        adjusted = max(0.0, max_allowed - tax_before_surcharge)
        return Surcharge(adjusted, raw - adjusted, rate)
    return Surcharge(raw, 0.0, rate)


def india_tax(
    salary: float,
    *,
    fy: str = LATEST_INDIA_FY,
    regime: str = "new",
    age_band: str = "below60",
    deductions: Optional[IndiaDeductions] = None,
) -> IndiaTax:
    """Tax on a resident individual's salary for one regime (``calculateTaxForRegime``).

    Old-regime deductions are capped as tax-break caps them; the new regime
    allows only the standard deduction. Home-loan interest is the
    self-occupied 24(b) deduction, set off against salary in the old regime.
    """

    year = india_year(fy)
    rules = year.rules(regime)
    slabs = rules.slabs(age_band)
    claims = deductions or IndiaDeductions()
    pay = max(0.0, float(salary))

    house_property = 0.0
    if regime == "old" and claims.home_loan_interest > 0:
        interest = min(max(0.0, claims.home_loan_interest), HOME_LOAN_INTEREST_CAP)
        house_property = max(-interest, -HOUSE_PROPERTY_LOSS_CAP)
    gross_total = pay + house_property
    standard = min(rules.standard_deduction, pay)

    c80 = d80 = ccd = e80 = g80 = 0.0
    if regime == "new":
        total_deductions = standard
    else:
        c80 = min(max(0.0, claims.section_80c), SECTION_80C_CAP)
        self_cap = SECTION_80D_SENIOR_CAP if age_band != "below60" else SECTION_80D_CAP
        parents_cap = SECTION_80D_SENIOR_CAP if claims.parents_senior else SECTION_80D_CAP
        d80 = min(max(0.0, claims.section_80d_self), self_cap) + min(
            max(0.0, claims.section_80d_parents), parents_cap
        )
        ccd = min(max(0.0, claims.section_80ccd1b), SECTION_80CCD1B_CAP)
        e80 = max(0.0, claims.section_80e)
        g80 = max(0.0, claims.section_80g)
        total_deductions = c80 + d80 + ccd + 0.0 + e80 + g80 + standard

    taxable = max(0.0, gross_total - total_deductions)
    before = slab_tax(taxable, slabs)
    rebate = rebate_87a(taxable, before, rules)
    after = max(0.0, before - rebate)
    surcharge = india_surcharge(taxable, after, rules.surcharge_tiers, slabs)
    with_surcharge = after + surcharge.amount
    cess = with_surcharge * rules.cess_rate
    unrounded = with_surcharge + cess
    total = _js_round(unrounded)
    effective = total / gross_total * 100 if gross_total > 0 else 0.0
    return IndiaTax(
        fy=year.key, label=year.label, regime=regime, age_band=age_band, salary=pay,
        house_property=house_property, gross_total_income=gross_total,
        standard_deduction=standard, section_80c=c80, section_80d=d80,
        section_80ccd1b=ccd, section_80e=e80, section_80g=g80,
        total_deductions=total_deductions, taxable_income=taxable,
        tax_before_rebate=before, rebate=rebate, tax_after_rebate=after,
        surcharge=surcharge.amount, surcharge_rate=surcharge.rate,
        marginal_relief=surcharge.marginal_relief, cess=cess,
        unrounded_total=unrounded, total=total, effective_rate=effective,
    )


def india_compare(
    salary: float,
    *,
    fy: str = LATEST_INDIA_FY,
    age_band: str = "below60",
    deductions: Optional[IndiaDeductions] = None,
) -> IndiaComparison:
    """Compute both regimes; the new regime wins ties, as in ``compareRegimes``."""

    old = india_tax(salary, fy=fy, regime="old", age_band=age_band, deductions=deductions)
    new = india_tax(salary, fy=fy, regime="new", age_band=age_band, deductions=deductions)
    recommended = "new" if new.total <= old.total else "old"
    return IndiaComparison(old, new, recommended, abs(old.total - new.total))


# --------------------------------------------------------------------------
# United Kingdom 2025/26: calculators/uk.ts
# --------------------------------------------------------------------------

UK_TAX_YEAR = "2025/26"
UK_PERSONAL_ALLOWANCE = 12570.0
UK_TAPER_THRESHOLD = 100000.0
UK_BASIC_RATE_LIMIT = 37700.0
UK_HIGHER_RATE_LIMIT = 125140.0
UK_NI_PRIMARY_THRESHOLD = 12570.0
UK_NI_UPPER_EARNINGS_LIMIT = 50270.0

UK_STUDENT_LOAN_PLANS: Dict[str, Tuple[float, float]] = {
    "plan1": (26065.0, 0.09),
    "plan2": (28470.0, 0.09),
    "plan4": (32745.0, 0.09),
    "plan5": (25000.0, 0.09),
    "postgraduate": (21000.0, 0.06),
}


@dataclass(frozen=True)
class UkTax:
    """Income tax, employee Class 1 NI and student loan on UK employment income."""

    gross_income: float
    adjusted_net_income: float
    personal_allowance: float
    taxable_income: float
    basic_rate_income: float
    higher_rate_income: float
    additional_rate_income: float
    income_tax: float
    national_insurance: float
    student_loan_plan: Optional[str]
    student_loan: float
    total: float
    take_home: float
    effective_rate: float


def uk_personal_allowance(adjusted_net_income: float) -> float:
    """£12,570, reduced by £1 for every £2 of income over £100,000."""

    if adjusted_net_income <= UK_TAPER_THRESHOLD:
        return UK_PERSONAL_ALLOWANCE
    return max(0.0, UK_PERSONAL_ALLOWANCE - (adjusted_net_income - UK_TAPER_THRESHOLD) / 2)


def uk_national_insurance(earnings: float) -> float:
    """Employee Class 1 NI: 8% from £12,570 to £50,270 and 2% above."""

    earnings = max(0.0, earnings)
    main_band = max(0.0, min(earnings, UK_NI_UPPER_EARNINGS_LIMIT) - UK_NI_PRIMARY_THRESHOLD)
    upper_band = max(0.0, earnings - UK_NI_UPPER_EARNINGS_LIMIT)
    return _round2(main_band * 0.08 + upper_band * 0.02)


def uk_student_loan(income: float, plan: Optional[str]) -> float:
    """Annual repayment, to the nearest pound, for a plan in :data:`UK_STUDENT_LOAN_PLANS`."""

    if plan is None or plan == "none":
        return 0.0
    if plan not in UK_STUDENT_LOAN_PLANS:
        raise ValueError(f"Unknown student loan plan {plan!r}.")
    threshold, rate = UK_STUDENT_LOAN_PLANS[plan]
    return _js_round(max(0.0, income - threshold) * rate)


def uk_tax(salary: float, *, student_loan_plan: Optional[str] = None) -> UkTax:
    """England, Wales and Northern Ireland tax on salary (``calculateUkTax``)."""

    plan = None if student_loan_plan in (None, "none") else student_loan_plan
    if plan is not None and plan not in UK_STUDENT_LOAN_PLANS:
        raise ValueError(f"Unknown student loan plan {plan!r}.")
    pay = max(0.0, float(salary))
    gross = _round2(pay)
    non_savings = _round2(pay)
    adjusted = _round2(max(0.0, gross))
    allowance = _round2(uk_personal_allowance(adjusted))
    taxable = _round2(non_savings - min(allowance, non_savings))
    basic = max(0.0, min(taxable, UK_BASIC_RATE_LIMIT))
    higher = max(0.0, min(taxable, UK_HIGHER_RATE_LIMIT) - UK_BASIC_RATE_LIMIT)
    additional = max(0.0, taxable - UK_HIGHER_RATE_LIMIT)
    income_tax = _round2(_round2(basic * 0.2 + higher * 0.4 + additional * 0.45))
    national_insurance = uk_national_insurance(pay)
    student_loan = uk_student_loan(pay, plan)
    total = _round2(income_tax + national_insurance + student_loan)
    return UkTax(
        gross_income=gross, adjusted_net_income=adjusted, personal_allowance=allowance,
        taxable_income=_round2(taxable), basic_rate_income=basic,
        higher_rate_income=higher, additional_rate_income=additional,
        income_tax=income_tax, national_insurance=national_insurance,
        student_loan_plan=plan, student_loan=student_loan, total=total,
        take_home=_round2(gross - total),
        effective_rate=total / gross * 100 if gross > 0 else 0.0,
    )


# --------------------------------------------------------------------------
# United States 2025: calculators/us.ts and usState.ts
# --------------------------------------------------------------------------

US_TAX_YEAR = "2025"
US_FILING_STATUSES: Dict[str, str] = {
    "single": "single",
    "married_joint": "married filing jointly",
    "married_separate": "married filing separately",
    "head_of_household": "head of household",
}
US_STANDARD_DEDUCTION: Dict[str, float] = {
    "single": 15750.0,
    "married_joint": 31500.0,
    "married_separate": 15750.0,
    "head_of_household": 23625.0,
}
_US_FEDERAL_BRACKETS: Dict[str, Tuple[Bracket, ...]] = {
    "single": _bands(
        (0, 0.1), (11925, 0.12), (48475, 0.22), (103350, 0.24), (197300, 0.32),
        (250525, 0.35), (626350, 0.37),
    ),
    "married_joint": _bands(
        (0, 0.1), (23850, 0.12), (96950, 0.22), (206700, 0.24), (394600, 0.32),
        (501050, 0.35), (751600, 0.37),
    ),
    "married_separate": _bands(
        (0, 0.1), (11925, 0.12), (48475, 0.22), (103350, 0.24), (197300, 0.32),
        (250525, 0.35), (375800, 0.37),
    ),
    "head_of_household": _bands(
        (0, 0.1), (17000, 0.12), (64850, 0.22), (103350, 0.24), (197300, 0.32),
        (250500, 0.35), (626350, 0.37),
    ),
}
_US_CTC_PHASE_OUT: Dict[str, float] = {
    "single": 200000.0,
    "married_joint": 400000.0,
    "married_separate": 200000.0,
    "head_of_household": 200000.0,
}
_US_ADDITIONAL_MEDICARE_THRESHOLD: Dict[str, float] = {
    "single": 200000.0,
    "married_joint": 250000.0,
    "married_separate": 125000.0,
    "head_of_household": 200000.0,
}
US_CHILD_TAX_CREDIT = 2200.0
US_SOCIAL_SECURITY_WAGE_BASE = 176100.0


@dataclass(frozen=True)
class UsStateRules:
    """A state's single-filer deduction, exemption and brackets (empty: no wage tax)."""

    code: str
    name: str
    standard_deduction: float
    personal_exemption: float
    brackets: Tuple[Bracket, ...]


@dataclass(frozen=True)
class UsStateTax:
    code: str
    name: str
    deduction: float
    taxable_income: float
    tax: float


@dataclass(frozen=True)
class UsTax:
    """Federal income tax, FICA and optional state tax on wages."""

    filing_status: str
    gross_income: float
    adjusted_gross_income: float
    standard_deduction: float
    taxable_income: float
    federal_income_tax: float
    children: int
    child_tax_credit: float
    fica: float
    additional_medicare: float
    state: Optional[UsStateTax]
    total: float
    take_home: float
    effective_rate: float


def _state(code: str, name: str, deduction: float = 0, exemption: float = 0,
           *points: Tuple[float, float]) -> UsStateRules:
    return UsStateRules(code, name, float(deduction), float(exemption), _bands(*points) if points else ())


US_STATES: Dict[str, UsStateRules] = {
    rules.code: rules
    for rules in (
        _state("AL", "Alabama", 2500, 1500, (0, 0.02), (500, 0.04), (3000, 0.05)),
        _state("AK", "Alaska"),
        _state("AZ", "Arizona", 15750, 0, (0, 0.025)),
        _state("AR", "Arkansas", 2410, 0, (0, 0), (5500, 0.02), (10900, 0.03), (15600, 0.034),
               (25700, 0.039)),
        _state("CA", "California", 5706, 0, (0, 0.01), (10756, 0.02), (25499, 0.04),
               (40245, 0.06), (55866, 0.08), (70606, 0.093), (360659, 0.103), (432787, 0.113),
               (721314, 0.123), (1000000, 0.133)),
        _state("CO", "Colorado", 15750, 0, (0, 0.044)),
        _state("CT", "Connecticut", 0, 15000, (0, 0.03), (10000, 0.05), (50000, 0.055),
               (100000, 0.06), (200000, 0.065), (250000, 0.069), (500000, 0.0699)),
        _state("DE", "Delaware", 3250, 110, (0, 0), (2000, 0.022), (5000, 0.039),
               (10000, 0.048), (20000, 0.052), (25000, 0.0555), (60000, 0.066)),
        _state("DC", "District of Columbia", 5650, 0, (0, 0.04), (10000, 0.06), (40000, 0.065),
               (60000, 0.085), (250000, 0.0925), (500000, 0.0975), (1000000, 0.1075)),
        _state("FL", "Florida"),
        _state("GA", "Georgia", 5400, 0, (0, 0.0519)),
        _state("HI", "Hawaii", 2200, 1144, (0, 0.014), (9600, 0.032), (14400, 0.055),
               (19200, 0.064), (24000, 0.068), (36000, 0.072), (48000, 0.076), (125000, 0.079),
               (175000, 0.0825), (225000, 0.09), (275000, 0.1), (325000, 0.11)),
        _state("ID", "Idaho", 15750, 0, (0, 0.058)),
        _state("IL", "Illinois", 0, 2765, (0, 0.0495)),
        _state("IN", "Indiana", 0, 1000, (0, 0.0305)),
        _state("IA", "Iowa", 15750, 0, (0, 0.038)),
        _state("KS", "Kansas", 3500, 2225, (0, 0.052), (23000, 0.0558)),
        _state("KY", "Kentucky", 2980, 0, (0, 0.04)),
        _state("LA", "Louisiana", 4500, 1000, (0, 0.03)),
        _state("ME", "Maine", 15000, 5150, (0, 0.058), (26799, 0.0675), (63449, 0.0715)),
        _state("MD", "Maryland", 2500, 3200, (0, 0.02), (1000, 0.03), (2000, 0.04),
               (3000, 0.0475), (100000, 0.05), (125000, 0.0525), (150000, 0.055),
               (250000, 0.0575)),
        _state("MA", "Massachusetts", 0, 4400, (0, 0.05), (1083150, 0.09)),
        _state("MI", "Michigan", 0, 5400, (0, 0.0425)),
        _state("MN", "Minnesota", 14950, 0, (0, 0.0535), (32570, 0.068), (106990, 0.0785),
               (198630, 0.0985)),
        _state("MS", "Mississippi", 2300, 6000, (0, 0), (10000, 0.044)),
        _state("MO", "Missouri", 15750, 0, (0, 0), (1121, 0.015), (2242, 0.02), (3363, 0.025),
               (4484, 0.03), (5605, 0.035), (6726, 0.04), (7847, 0.045), (8968, 0.048)),
        _state("MT", "Montana", 15750, 0, (0, 0.047), (20500, 0.059)),
        _state("NE", "Nebraska", 8600, 0, (0, 0.0246), (4030, 0.0351), (24120, 0.0501),
               (38870, 0.052)),
        _state("NV", "Nevada"),
        _state("NH", "New Hampshire"),
        _state("NJ", "New Jersey", 0, 1000, (0, 0.014), (20000, 0.0175), (35000, 0.035),
               (40000, 0.05525), (75000, 0.0637), (500000, 0.0897), (1000000, 0.1075)),
        _state("NM", "New Mexico", 15750, 0, (0, 0.015), (5500, 0.032), (16500, 0.043),
               (33500, 0.047), (66500, 0.049), (210000, 0.059)),
        _state("NY", "New York", 8000, 0, (0, 0.04), (8500, 0.045), (11700, 0.0525),
               (13900, 0.055), (80650, 0.06), (215400, 0.0685), (1077550, 0.0965),
               (5000000, 0.103), (25000000, 0.109)),
        _state("NC", "North Carolina", 7500, 0, (0, 0.0475)),
        _state("ND", "North Dakota", 15750, 0, (0, 0), (48475, 0.0195), (244825, 0.025)),
        _state("OH", "Ohio", 0, 2650, (0, 0), (26050, 0.0275), (100000, 0.03125)),
        _state("OK", "Oklahoma", 6350, 1000, (0, 0.0025), (999, 0.0075), (2499, 0.0175),
               (3749, 0.0275), (4899, 0.0375), (7199, 0.0475)),
        _state("OR", "Oregon", 2835, 0, (0, 0.0475), (4400, 0.0675), (11050, 0.0875),
               (125000, 0.099)),
        _state("PA", "Pennsylvania", 0, 0, (0, 0.0307)),
        _state("RI", "Rhode Island", 10900, 5100, (0, 0.0375), (79900, 0.0475),
               (181650, 0.0599)),
        _state("SC", "South Carolina", 15750, 4770, (0, 0), (3460, 0.03), (17330, 0.06)),
        _state("SD", "South Dakota"),
        _state("TN", "Tennessee"),
        _state("TX", "Texas"),
        _state("UT", "Utah", 15750, 0, (0, 0.0465)),
        _state("VT", "Vermont", 7650, 5300, (0, 0.0335), (47900, 0.066), (116000, 0.076),
               (242000, 0.0875)),
        _state("VA", "Virginia", 8500, 930, (0, 0.02), (3000, 0.03), (5000, 0.05),
               (17000, 0.0575)),
        _state("WA", "Washington"),
        _state("WV", "West Virginia", 2000, 2000, (0, 0.0222), (10000, 0.0296),
               (25000, 0.0333), (40000, 0.0444), (60000, 0.0482)),
        _state("WI", "Wisconsin", 13930, 700, (0, 0.035), (14319, 0.044), (28639, 0.053),
               (315309, 0.0765)),
        _state("WY", "Wyoming"),
    )
}


def _filing_status(filing_status: str) -> str:
    if filing_status not in US_FILING_STATUSES:
        raise ValueError(
            f"Unknown filing status {filing_status!r}; use one of {tuple(US_FILING_STATUSES)}."
        )
    return filing_status


def us_fica(wages: float) -> float:
    """Employee Social Security (6.2% up to the wage base) plus Medicare (1.45%)."""

    earnings = max(0.0, wages)
    return _round2(min(earnings, US_SOCIAL_SECURITY_WAGE_BASE) * 0.062 + earnings * 0.0145)


def us_child_tax_credit(children: int, agi: float, filing_status: str = "single") -> float:
    """$2,200 per child under 17, less $50 per $1,000 (or part) of AGI over the threshold."""

    base = max(0, children) * US_CHILD_TAX_CREDIT
    if base <= 0:
        return 0.0
    excess = max(0.0, agi - _US_CTC_PHASE_OUT[_filing_status(filing_status)])
    reduction = math.ceil(excess / 1000) * 50
    return _round2(max(0.0, base - reduction))


def us_state_tax(income: float, code: str) -> UsStateTax:
    """2025 single-filer state income tax on ``income`` (``calculateUsStateTax``)."""

    key = str(code).upper()
    if key not in US_STATES:
        raise ValueError(f"Unknown US state code {code!r}.")
    rules = US_STATES[key]
    income = max(0.0, income)
    deduction = min(income, rules.standard_deduction + rules.personal_exemption)
    taxable = income - deduction
    tax = _js_round(slab_tax(taxable, rules.brackets) * 100) / 100
    return UsStateTax(rules.code, rules.name, deduction, taxable, tax)


def us_tax(
    wages: float,
    *,
    filing_status: str = "single",
    state: Optional[str] = None,
    children: int = 0,
) -> UsTax:
    """Federal tax with the standard deduction, FICA and optional state tax (``calculateUsTax``)."""

    status = _filing_status(filing_status)
    pay = max(0.0, float(wages))
    gross = _round2(_round2(pay) + 0.0)
    agi = _round2(max(0.0, gross))
    standard = US_STANDARD_DEDUCTION[status]
    taxable = _round2(max(0.0, agi - standard))
    federal = _round2(_round2(slab_tax(_round2(max(0.0, taxable)), _US_FEDERAL_BRACKETS[status])))
    kids = max(0, int(children))
    credits = _round2(min(federal, us_child_tax_credit(kids, agi, status)))
    fica = us_fica(pay)
    additional = _round2(max(0.0, pay - _US_ADDITIONAL_MEDICARE_THRESHOLD[status]) * 0.009)
    state_tax = us_state_tax(gross, state) if state else None
    total = _round2(
        federal - credits + fica + additional + (state_tax.tax if state_tax else 0.0)
    )
    return UsTax(
        filing_status=status, gross_income=gross, adjusted_gross_income=agi,
        standard_deduction=standard, taxable_income=taxable, federal_income_tax=federal,
        children=kids, child_tax_credit=credits, fica=fica, additional_medicare=additional,
        state=state_tax, total=total, take_home=_round2(gross - total),
        effective_rate=total / gross * 100 if gross > 0 else 0.0,
    )


# --------------------------------------------------------------------------
# Ireland 2025: calculators/ireland.ts
# --------------------------------------------------------------------------

IRELAND_TAX_YEAR = "2025"
IRELAND_FILING_STATUSES: Dict[str, str] = {
    "single": "single",
    "single_parent": "single parent",
    "married_one_income": "married or in a civil partnership, one income",
    "married_two_incomes": "married or in a civil partnership, two incomes",
}
_IRELAND_CUT_OFF: Dict[str, float] = {
    "single": 44000.0,
    "single_parent": 48000.0,
    "married_one_income": 53000.0,
    "married_two_incomes": 53000.0,
}
_IRELAND_PERSONAL_CREDIT: Dict[str, float] = {
    "single": 2000.0,
    "single_parent": 3900.0,
    "married_one_income": 4000.0,
    "married_two_incomes": 4000.0,
}
IRELAND_EMPLOYEE_CREDIT = 2000.0
_IRELAND_CUT_OFF_INCREASE_CAP = 35000.0
_IRELAND_USC_BANDS = _bands((0, 0.005), (12012, 0.02), (27382, 0.03), (70044, 0.08))
IRELAND_USC_EXEMPTION = 13000.0
IRELAND_PRSI_RATE = 0.041
IRELAND_PRSI_EXEMPTION = 352.0 * 52


@dataclass(frozen=True)
class IrelandTax:
    """PAYE income tax, credits, USC and Class A PRSI."""

    filing_status: str
    gross_income: float
    taxable_income: float
    standard_rate_cut_off: float
    income_tax: float
    personal_credit: float
    employee_credit: float
    tax_credits: float
    usc: float
    prsi: float
    total: float
    take_home: float
    effective_rate: float


def _ireland_status(filing_status: str) -> str:
    if filing_status not in IRELAND_FILING_STATUSES:
        raise ValueError(
            f"Unknown filing status {filing_status!r}; use one of {tuple(IRELAND_FILING_STATUSES)}."
        )
    return filing_status


def ireland_standard_rate_cut_off(filing_status: str = "single", spouse_income: float = 0.0) -> float:
    """Income taxed at 20%; a second earner adds up to €35,000."""

    status = _ireland_status(filing_status)
    base = _IRELAND_CUT_OFF[status]
    if status != "married_two_incomes":
        return base
    return base + min(max(0.0, spouse_income), _IRELAND_CUT_OFF_INCREASE_CAP)


def ireland_usc(gross_income: float) -> float:
    """Universal Social Charge; nothing is due on €13,000 or less."""

    if gross_income <= IRELAND_USC_EXEMPTION:
        return 0.0
    return _round2(slab_tax(gross_income, _IRELAND_USC_BANDS))


def ireland_prsi(gross_income: float) -> float:
    """Class A employee PRSI at 4.1% on all income once over €352 a week."""

    if gross_income <= IRELAND_PRSI_EXEMPTION:
        return 0.0
    return _round2(gross_income * IRELAND_PRSI_RATE)


def ireland_tax(
    salary: float, *, filing_status: str = "single", spouse_income: float = 0.0
) -> IrelandTax:
    """Tax on a PAYE employee's salary (``calculateIrelandTax``)."""

    status = _ireland_status(filing_status)
    spouse = max(0.0, spouse_income)
    pay = max(0.0, float(salary))
    taxable = _round2(max(0.0, pay))
    cut_off = ireland_standard_rate_cut_off(status, spouse)
    income_tax = _round2(slab_tax(taxable, _bands((0, 0.2), (cut_off, 0.4))))
    employee_credit = (IRELAND_EMPLOYEE_CREDIT if pay > 0 else 0.0) + (
        IRELAND_EMPLOYEE_CREDIT if status == "married_two_incomes" and spouse > 0 else 0.0
    )
    personal_credit = _IRELAND_PERSONAL_CREDIT[status]
    credits = _round2(min(income_tax, personal_credit + employee_credit))
    usc = ireland_usc(pay)
    prsi = ireland_prsi(pay)
    total = _round2(income_tax - credits + usc + prsi)
    return IrelandTax(
        filing_status=status, gross_income=pay, taxable_income=taxable,
        standard_rate_cut_off=cut_off, income_tax=income_tax,
        personal_credit=personal_credit, employee_credit=employee_credit,
        tax_credits=credits, usc=usc, prsi=prsi, total=total,
        take_home=_round2(pay - total),
        effective_rate=total / pay * 100 if pay > 0 else 0.0,
    )


# --------------------------------------------------------------------------
# Netherlands 2025: calculators/netherlands.ts
# --------------------------------------------------------------------------

NETHERLANDS_TAX_YEAR = "2025"
_DUTCH_BOX1_BRACKETS = _bands((0, 0.3582), (38441, 0.3748), (76817, 0.495))
_DUTCH_RULING_CAP = 246000.0


@dataclass(frozen=True)
class NetherlandsTax:
    """Box 1 tax on salary less the general and labour tax credits."""

    gross_income: float
    thirty_percent_ruling: bool
    ruling_exemption: float
    taxable_employment_income: float
    box1_income: float
    box1_tax: float
    general_tax_credit: float
    labour_tax_credit: float
    tax_credits: float
    total: float
    take_home: float
    effective_rate: float


def dutch_general_tax_credit(income: float) -> float:
    """Algemene heffingskorting: €3,068, phased out between €28,406 and €76,817."""

    if income <= 28406:
        return 3068.0
    if income >= 76817:
        return 0.0
    return max(0.0, 3068 - 0.06337 * (income - 28406))


def dutch_labour_tax_credit(income: float) -> float:
    """Arbeidskorting: builds up to €5,599, then phases out to nil at €129,078."""

    if income <= 12169:
        return 0.08053 * income
    if income <= 26288:
        return 980 + 0.3003 * (income - 12169)
    if income <= 43071:
        return 5220 + 0.02258 * (income - 26288)
    if income >= 129078:
        return 0.0
    return max(0.0, 5599 - 0.0651 * (income - 43071))


def dutch_thirty_percent_exemption(employment_income: float) -> float:
    """Tax-free part under the 30% ruling: 30% of salary up to €246,000."""

    return 0.3 * min(employment_income, _DUTCH_RULING_CAP)


def netherlands_tax(salary: float, *, thirty_percent_ruling: bool = False) -> NetherlandsTax:
    """Box 1 tax on salary for someone below AOW age (``calculateNetherlandsTax``)."""

    pay = max(0.0, float(salary))
    exemption = _round2(dutch_thirty_percent_exemption(pay)) if thirty_percent_ruling else 0.0
    taxable_employment = _round2(pay - exemption)
    box1_income = _round2(max(0.0, _round2(taxable_employment)))
    box1_tax = _round2(_round2(slab_tax(box1_income, _DUTCH_BOX1_BRACKETS)))
    general = _round2(dutch_general_tax_credit(box1_income))
    labour = _round2(dutch_labour_tax_credit(taxable_employment))
    credits = _round2(min(box1_tax, general + labour))
    total = _round2(box1_tax - credits)
    gross = _round2(pay)
    return NetherlandsTax(
        gross_income=gross, thirty_percent_ruling=bool(thirty_percent_ruling),
        ruling_exemption=exemption, taxable_employment_income=taxable_employment,
        box1_income=box1_income, box1_tax=box1_tax, general_tax_credit=general,
        labour_tax_credit=labour, tax_credits=credits, total=total,
        take_home=_round2(gross - total),
        effective_rate=total / gross * 100 if gross > 0 else 0.0,
    )


# --------------------------------------------------------------------------
# Singapore YA 2025: calculators/singapore.ts
# --------------------------------------------------------------------------

SINGAPORE_YEAR_OF_ASSESSMENT = "2025"
SINGAPORE_AGE_BANDS: Tuple[str, ...] = ("below55", "55to59", "60plus")
_SINGAPORE_SLABS = _bands(
    (0, 0), (20000, 0.02), (30000, 0.035), (40000, 0.07), (80000, 0.115), (120000, 0.15),
    (160000, 0.18), (200000, 0.19), (240000, 0.195), (280000, 0.2), (320000, 0.22),
    (500000, 0.23), (1000000, 0.24),
)
_SINGAPORE_EARNED_INCOME_RELIEF: Dict[str, float] = {
    "below55": 1000.0,
    "55to59": 6000.0,
    "60plus": 8000.0,
}
SINGAPORE_RELIEF_CAP = 80000.0


@dataclass(frozen=True)
class SingaporeTax:
    """Resident tax on employment income after earned income and CPF relief."""

    age_band: str
    gross_income: float
    earned_income_relief: float
    cpf_relief: float
    total_reliefs: float
    chargeable_income: float
    income_tax: float
    rebate: float
    total: float
    after_tax: float
    effective_rate: float


def singapore_age_band(age: Optional[int]) -> str:
    """Map an age to the earned-income-relief band."""

    if age is None or age < 55:
        return "below55"
    return "55to59" if age < 60 else "60plus"


def singapore_earned_income_relief(earned_income: float, age_band: str = "below55") -> float:
    """S$1,000, S$6,000 or S$8,000 by age, never more than the income itself."""

    if age_band not in _SINGAPORE_EARNED_INCOME_RELIEF:
        raise ValueError(f"Unknown age band {age_band!r}; use one of {SINGAPORE_AGE_BANDS}.")
    return min(max(0.0, earned_income), _SINGAPORE_EARNED_INCOME_RELIEF[age_band])


def singapore_tax(
    salary: float, *, age_band: str = "below55", cpf_contributions: float = 0.0
) -> SingaporeTax:
    """YA 2025 resident tax on salary (``calculateSingaporeTax``)."""

    employment = _round2(max(0.0, float(salary)))
    gross = _round2(employment)
    assessable = _round2(max(0.0, gross))
    earned_relief = singapore_earned_income_relief(employment, age_band)
    cpf_relief = _round2(max(0.0, cpf_contributions))
    reliefs = min(_round2(earned_relief + cpf_relief), SINGAPORE_RELIEF_CAP)
    chargeable = _round2(max(0.0, assessable - reliefs))
    income_tax = _round2(slab_tax(chargeable, _SINGAPORE_SLABS))
    rebate = _round2(min(income_tax * 0.6, 200))
    total = _round2(income_tax - rebate)
    return SingaporeTax(
        age_band=age_band, gross_income=gross, earned_income_relief=earned_relief,
        cpf_relief=cpf_relief, total_reliefs=reliefs, chargeable_income=chargeable,
        income_tax=income_tax, rebate=rebate, total=total,
        after_tax=_round2(gross - total),
        effective_rate=total / gross * 100 if gross > 0 else 0.0,
    )


# --------------------------------------------------------------------------
# Plain-text replies
# --------------------------------------------------------------------------

_SYMBOLS: Dict[str, str] = {
    "india": "₹", "uk": "£", "us": "$", "ireland": "€", "netherlands": "€", "singapore": "S$",
}
_LATEST = "the latest in tax-break's tables"
_MARGINAL_STEP = 1000.0
_MARGINAL_REASONS: Dict[str, str] = {
    "india": "as the 87A rebate or surcharge marginal relief tapers off",
    "uk": "as the personal allowance is withdrawn",
    "ireland": "as PRSI or USC starts to apply",
}
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
_TABLES_HELD: Dict[str, Tuple[str, str]] = {
    "india": ("India tables for FY 2021-22 to FY 2025-26", "FY 2025-26"),
    "uk": ("a UK table for 2025/26 only", "2025/26"),
    "us": ("US tables for 2025 only", "2025"),
    "ireland": ("an Irish table for 2025 only", "2025"),
    "netherlands": ("a Dutch table for 2025 only", "2025"),
    "singapore": ("a Singapore table for YA 2025 only", "YA 2025"),
}
_FY2024_25_NOTE = (
    "tax-break's FY 2024-25 new-regime slabs are the earlier 3/6/9/12/15 lakh ones; the July "
    "2024 Budget changed them to 3/7/10/12/15 lakh, so the new-regime figure may be up to "
    "₹10,000 too high before cess and surcharge."
)
_PRSI_NOTE = (
    "tax-break charges PRSI at 4.1% for all of 2025, but the rate was scheduled to rise to "
    "4.2% from 1 October 2025, so the PRSI figure may be slightly low."
)


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

    cents = int(_js_round(abs(value))) * 100 if whole else int(_js_round(abs(value) * 100))
    units, fraction = divmod(cents, 100)
    digits = _group_indian(str(units)) if symbol == "₹" else f"{units:,}"
    text = symbol + digits + (f".{fraction:02d}" if fraction else "")
    return "-" + text if value < 0 and cents else text


def _pct(value: float) -> str:
    """A percentage to one decimal place, without a trailing ".0"."""

    if abs(value) < 0.05:
        return "0%"
    return f"{value:.1f}".rstrip("0").rstrip(".") + "%"


def _rate_text(rate: float) -> str:
    """A tax rate such as 0.3582 written as "35.82%"."""

    return f"{rate * 100:.4f}".rstrip("0").rstrip(".") + "%"


def _band_split(income: float, brackets: Sequence[Bracket]) -> List[Tuple[float, float]]:
    """Return ``(rate, amount)`` for each band that ``income`` reaches."""

    parts = []
    for bracket in brackets:
        if income <= bracket.lower:
            break
        upper = income if bracket.upper is None else min(income, bracket.upper)
        parts.append((bracket.rate, upper - bracket.lower))
    return parts


def _band_text(parts: Sequence[Tuple[float, float]], symbol: str) -> str:
    return ", ".join(
        f"{_rate_text(rate)} on {_money(amount, symbol)}" for rate, amount in parts if amount > 0
    )


def _marginal(total_at: Callable[[float], float], income: float) -> float:
    """Extra tax on the next 1,000 of salary, as a percentage of that 1,000."""

    return (total_at(income + _MARGINAL_STEP) - total_at(income)) / _MARGINAL_STEP * 100


def _rates_line(country: str, effective: float, marginal: float) -> str:
    step = _money(_MARGINAL_STEP, _SYMBOLS[country])
    line = f"- Rates: {_pct(effective)} effective, {_pct(marginal)} marginal on the next {step}"
    if marginal >= 60:
        reason = _MARGINAL_REASONS.get(country, "as a credit phases out or a threshold is crossed")
        line += f" ({reason})"
    return line


def _year_line(heading: str, label: str, defaulted: bool) -> str:
    return f"{heading}: {label}" + (f", {_LATEST}." if defaulted else ".")


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


def _india_claims(req: "_Request") -> IndiaDeductions:
    stated = req.deductions
    return IndiaDeductions(
        section_80c=stated.get("section_80c", 0.0),
        section_80d_self=stated.get("section_80d_self", 0.0),
        section_80d_parents=stated.get("section_80d_parents", 0.0),
        parents_senior=req.parents_senior,
        section_80ccd1b=stated.get("section_80ccd1b", 0.0),
        section_80e=stated.get("section_80e", 0.0),
        section_80g=stated.get("section_80g", 0.0),
        home_loan_interest=stated.get("home_loan_interest", 0.0),
    )


def _india_block(result: IndiaTax, claims: IndiaDeductions, req: "_Request") -> List[str]:
    symbol = _SYMBOLS["india"]
    lines: List[str] = []
    old = result.regime == "old"
    if old and claims.home_loan_interest > 0:
        allowed = -result.house_property
        lines.append(
            f"- Home-loan interest 24(b): {_money(allowed, symbol)} set off against salary"
            + _claim_suffix(claims.home_loan_interest, allowed, symbol)
        )
    rows = (
        ("80C", claims.section_80c, result.section_80c),
        ("80D", claims.section_80d_self + claims.section_80d_parents, result.section_80d),
        ("NPS 80CCD(1B)", claims.section_80ccd1b, result.section_80ccd1b),
        ("80E", claims.section_80e, result.section_80e),
        ("80G", claims.section_80g, result.section_80g),
    )
    if old and any(claimed > 0 for _name, claimed, _allowed in rows):
        parts = [f"standard {_money(result.standard_deduction, symbol)}"]
        parts.extend(
            f"{name} {_money(allowed, symbol)}" + _claim_suffix(claimed, allowed, symbol)
            for name, claimed, allowed in rows
            if claimed > 0
        )
        lines.append("- Deductions: " + ", ".join(parts))
        basis = f"after {_money(result.total_deductions, symbol)} of deductions"
    elif result.standard_deduction > 0:
        basis = f"after the {_money(result.standard_deduction, symbol)} standard deduction"
    elif INDIA_YEARS[result.fy].rules(result.regime).standard_deduction == 0:
        fy_name = INDIA_YEARS[result.fy].label.split(" (")[0]
        basis = f"this regime had no standard deduction in {fy_name}"
    else:
        basis = ""
    lines.append(
        f"- Taxable income: {_money(result.taxable_income, symbol)}" + (f" ({basis})" if basis else "")
    )
    lines.append(f"- Tax on slabs: {_money(result.tax_before_rebate, symbol)}")
    if result.rebate > 0:
        lines.append(f"- Less rebate u/s 87A: {_money(result.rebate, symbol)}")
    if result.surcharge > 0 or result.marginal_relief > 0:
        line = f"- Surcharge ({_rate_text(result.surcharge_rate)}): {_money(result.surcharge, symbol)}"
        if result.marginal_relief > 0:
            line += f" after {_money(result.marginal_relief, symbol)} marginal relief"
        lines.append(line)
    if result.cess > 0:
        lines.append(f"- Health and education cess (4%): {_money(result.cess, symbol)}")
    lines.append(f"- Total tax: {_money(result.total, symbol)}")
    lines.append(_per_year_line("After income tax", result.salary - result.total, req, symbol))
    effective = result.total / result.salary * 100 if result.salary > 0 else 0.0
    marginal = _marginal(
        lambda pay: india_tax(
            pay, fy=result.fy, regime=result.regime, age_band=result.age_band, deductions=claims
        ).unrounded_total,
        result.salary,
    )
    lines.append(_rates_line("india", effective, marginal))
    return lines


def _india_reply(req: "_Request", fy: str, defaulted: bool, notes: List[str]) -> str:
    symbol = _SYMBOLS["india"]
    year = INDIA_YEARS[fy]
    age_band = india_age_band(req.age)
    claims = _india_claims(req)
    comparison = india_compare(req.income, fy=fy, age_band=age_band, deductions=claims)
    shown = ("new", "old") if req.regime is None else (req.regime,)
    assumptions = [f"resident individual {_INDIA_AGE_TEXT[age_band]}", "salary income only"]
    if not claims.claimed():
        assumptions.append("no deductions beyond the standard deduction")
    lines = [
        f"Indian income tax on {_income_phrase(req, symbol)}",
        _year_line("Financial year", year.label, defaulted),
        _assumptions(assumptions),
    ]
    for regime in shown:
        lines.append(f"{regime.capitalize()} regime:")
        lines.extend(_india_block(comparison.new if regime == "new" else comparison.old, claims, req))
    if req.regime is None:
        if comparison.old.total == comparison.new.total:
            lines.append("Both regimes come to the same tax.")
        else:
            lines.append(
                f"The {comparison.recommended} regime is lower by "
                f"{_money(comparison.savings, symbol)} a year."
            )
    else:
        other = comparison.old if req.regime == "new" else comparison.new
        lines.append(f"For comparison, the {other.regime} regime comes to {_money(other.total, symbol)}.")

    extra = list(notes)
    if fy == "FY2024-25" and "new" in shown:
        extra.append(_FY2024_25_NOTE)
    if claims.claimed() and shown == ("new",):
        extra.append(
            "The deductions you gave only lower the old-regime figure; the new regime allows "
            "just the standard deduction."
        )
    if not claims.claimed() and "old" in shown:
        extra.append(
            "Old-regime deductions such as 80C, 80D, NPS 80CCD(1B) and home-loan interest 24(b) "
            'would lower the old figure; add them, e.g. "80C 1.5 lakh".'
        )
    if age_band != "below60":
        extra.append("Age only changes the old-regime slabs and the 80D limit for your own health cover.")
    if claims.section_80g > 0:
        extra.append(
            "tax-break deducts 80G donations in full; many donations qualify for only 50% or are capped."
        )
    if _HRA.search(req.text):
        extra.append("HRA exemption isn't modelled, so the old-regime figure may be too high if you claim it.")
    if _CTC.search(req.text):
        extra.append(
            "The CTC is treated as taxable salary; employer PF and other untaxed parts of a CTC "
            "would lower the tax."
        )
    if _MARRIED.search(req.text):
        extra.append("Indian income tax is assessed per person; this is for one salary.")
    extra.append("After income tax is before EPF and professional tax.")
    return _finish(lines, extra)


def _uk_plan(text: str) -> Tuple[Optional[str], List[str]]:
    """Read a student loan plan from ``text``; returns the plan key and any notes."""

    notes: List[str] = []
    plans: List[str] = []
    for match in _UK_PLAN.finditer(text):
        number = _NUMBER_WORDS.get(match.group("plan").lower(), match.group("plan"))
        plans.append({"1": "plan1", "2": "plan2", "3": "postgraduate", "4": "plan4", "5": "plan5"}[str(number)])
        if str(number) == "3":
            notes.append("Plan 3 is the Postgraduate Loan, repaid at 6% above £21,000.")
    if _UK_POSTGRAD.search(text):
        plans.append("postgraduate")
    unique = list(dict.fromkeys(plans))
    if not unique:
        if _STUDENT_LOAN.search(text):
            notes.append('Say which student loan plan you have, e.g. "plan 2", to include repayments.')
        return None, notes
    if len(unique) > 1:
        notes.append(f"tax-break works out one loan at a time, so I used {_UK_PLAN_NAMES[unique[0]]} only.")
    if unique[0] == "plan5":
        notes.append("Plan 5 repayments start from April 2026, so none may be due in 2025/26.")
    return unique[0], notes


def _uk_reply(req: "_Request", defaulted: bool, notes: List[str]) -> str:
    symbol = _SYMBOLS["uk"]
    plan, plan_notes = _uk_plan(req.text)
    result = uk_tax(req.income, student_loan_plan=plan)
    assumptions = ["England, Wales or Northern Ireland rates", "salary only"]
    if plan is None:
        assumptions.append("no student loan")
    assumptions.append("no pension contributions")
    lines = [
        f"UK tax on {_income_phrase(req, symbol)}",
        _year_line("Tax year", f"{UK_TAX_YEAR} (6 April 2025 to 5 April 2026)", defaulted),
        _assumptions(assumptions),
    ]
    allowance = f"- Personal allowance: {_money(result.personal_allowance, symbol)}"
    if result.personal_allowance < UK_PERSONAL_ALLOWANCE:
        allowance += (
            f" ({_money(UK_PERSONAL_ALLOWANCE, symbol)} less £1 for every £2 over "
            f"{_money(UK_TAPER_THRESHOLD, symbol)})"
        )
    lines.append(allowance)
    lines.append(f"- Taxable income: {_money(result.taxable_income, symbol)}")
    bands = _band_text(
        ((0.2, result.basic_rate_income), (0.4, result.higher_rate_income),
         (0.45, result.additional_rate_income)),
        symbol,
    )
    lines.append(f"- Income tax: {_money(result.income_tax, symbol)}" + (f" ({bands})" if bands else ""))
    lines.append(
        f"- National Insurance: {_money(result.national_insurance, symbol)} "
        "(8% from £12,570 to £50,270, 2% above)"
    )
    if plan:
        threshold, rate = UK_STUDENT_LOAN_PLANS[plan]
        lines.append(
            f"- Student loan ({_UK_PLAN_NAMES[plan]}): {_money(result.student_loan, symbol)} "
            f"({_rate_text(rate)} above {_money(threshold, symbol)})"
        )
    lines.append(f"- Total: {_money(result.total, symbol)}")
    lines.append(_per_year_line("Take-home", result.take_home, req, symbol))
    marginal = _marginal(lambda pay: uk_tax(pay, student_loan_plan=plan).total, req.income)
    lines.append(_rates_line("uk", result.effective_rate, marginal))

    extra = list(notes) + plan_notes
    if _PENSION.search(req.text):
        extra.append(
            "Pension contributions aren't deducted; salary sacrifice or relief at source would "
            "lower the tax."
        )
    if req.age is not None and req.age >= 66:
        extra.append(
            "Employee National Insurance stops at State Pension age (66), but this figure still "
            "includes it."
        )
    if _KIDS.search(req.text) and req.income > 60000:
        extra.append("The High Income Child Benefit Charge isn't included.")
    if _MARRIED.search(req.text):
        extra.append("UK tax is per person; Marriage Allowance isn't included.")
    return _finish(lines, extra)


def _us_status(text: str) -> Tuple[str, List[str]]:
    if _US_MFS.search(text):
        return "married_separate", []
    if _US_HOH.search(text):
        return "head_of_household", []
    if _US_MFJ.search(text):
        return "married_joint", []
    if _MARRIED.search(text) and not _SINGLE.search(text):
        return "married_joint", ['I assumed married filing jointly; say "filing separately" if not.']
    return "single", []


def _us_reply(req: "_Request", state: Optional[str], defaulted: bool, notes: List[str]) -> str:
    symbol = _SYMBOLS["us"]
    status, status_notes = _us_status(req.text)
    result = us_tax(req.income, filing_status=status, state=state, children=req.children)
    where = f" in {US_STATES[state].name}" if state else ""
    assumptions = [US_FILING_STATUSES[status], "standard deduction", "wages only"]
    if not state:
        assumptions.append("no state tax")
    lines = [
        f"US tax on {_income_phrase(req, symbol)}{where}",
        _year_line("Tax year", US_TAX_YEAR, defaulted),
        _assumptions(assumptions),
        f"- Taxable income: {_money(result.taxable_income, symbol)} "
        f"(after the {_money(result.standard_deduction, symbol)} standard deduction)",
        f"- Federal income tax: {_money(result.federal_income_tax, symbol)}",
    ]
    if result.children:
        kids = f"{result.children} {'child' if result.children == 1 else 'children'} under 17"
        lines.append(
            f"- Less child tax credit: {_money(result.child_tax_credit, symbol)} "
            f"({kids}, {_money(US_CHILD_TAX_CREDIT, symbol)} each before limits)"
        )
    lines.append(
        f"- FICA: {_money(result.fica, symbol)} (Social Security 6.2% up to "
        f"{_money(US_SOCIAL_SECURITY_WAGE_BASE, symbol)}, Medicare 1.45%)"
    )
    if result.additional_medicare > 0:
        threshold = _US_ADDITIONAL_MEDICARE_THRESHOLD[status]
        lines.append(
            f"- Additional Medicare: {_money(result.additional_medicare, symbol)} "
            f"(0.9% above {_money(threshold, symbol)})"
        )
    if result.state is not None:
        state_tax = result.state
        if US_STATES[state_tax.code].brackets:
            line = f"- {state_tax.name} income tax: {_money(state_tax.tax, symbol)}"
            if state_tax.deduction > 0:
                line += f" (after {_money(state_tax.deduction, symbol)} of state deductions)"
            lines.append(line)
        else:
            lines.append(f"- {state_tax.name}: no state income tax on wages")
    lines.append(f"- Total: {_money(result.total, symbol)}")
    lines.append(_per_year_line("Take-home", result.take_home, req, symbol))
    marginal = _marginal(
        lambda pay: us_tax(pay, filing_status=status, state=state, children=req.children).total,
        req.income,
    )
    lines.append(_rates_line("us", result.effective_rate, marginal))

    extra = list(notes) + status_notes
    if state is None:
        extra.append('Add a state for state income tax, e.g. "in California".')
    elif US_STATES[state].brackets:
        if status != "single":
            extra.append(
                f"tax-break's state figures use single-filer rules, so a "
                f"{US_FILING_STATUSES[status]} {US_STATES[state].name} return may differ."
            )
        extra.append("Local income taxes and state credits aren't included.")
    if result.children:
        extra.append("I assumed the children are under 17.")
        if us_child_tax_credit(result.children, result.adjusted_gross_income, status) > result.child_tax_credit:
            extra.append(
                "The child tax credit is limited to the federal income tax here; any refundable "
                "part isn't included."
            )
    elif _KIDS.search(req.text) and not req.children_stated:
        extra.append("Say how many children under 17 you have to include the child tax credit.")
    if req.age is not None and req.age >= 65:
        extra.append("Extra deductions for people 65 and over aren't included.")
    if _PENSION.search(req.text):
        extra.append("401(k), IRA and other pre-tax contributions aren't deducted.")
    return _finish(lines, extra)


def _ireland_status_from_text(text: str) -> Tuple[str, List[str]]:
    if _IE_SINGLE_PARENT.search(text):
        return "single_parent", [
            "The single person child carer credit (€1,900) and the €48,000 20% band are included."
        ]
    if _MARRIED.search(text):
        return "married_one_income", [
            "For a married couple or civil partners I assumed one income; a second income can "
            "raise the 20% band by up to €35,000."
        ]
    return "single", []


def _ireland_reply(req: "_Request", defaulted: bool, notes: List[str]) -> str:
    symbol = _SYMBOLS["ireland"]
    status, status_notes = _ireland_status_from_text(req.text)
    result = ireland_tax(req.income, filing_status=status)
    who = {
        "single": "single PAYE employee",
        "single_parent": "single parent, PAYE employee",
        "married_one_income": "married or civil partners with one income, PAYE employee",
    }[status]
    lines = [
        f"Irish tax on {_income_phrase(req, symbol)}",
        _year_line("Tax year", IRELAND_TAX_YEAR, defaulted),
        _assumptions([who, "salary only"]),
    ]
    bands = _band_text(
        _band_split(result.taxable_income, _bands((0, 0.2), (result.standard_rate_cut_off, 0.4))),
        symbol,
    )
    lines.append(f"- Income tax: {_money(result.income_tax, symbol)}" + (f" ({bands})" if bands else ""))
    detail = (
        f"personal {_money(result.personal_credit, symbol)}, "
        f"employee {_money(result.employee_credit, symbol)}"
    )
    if result.tax_credits < result.personal_credit + result.employee_credit - 0.005:
        detail += ", limited to the tax"
    lines.append(f"- Less tax credits: {_money(result.tax_credits, symbol)} ({detail})")
    lines.append(
        f"- USC: {_money(result.usc, symbol)}" + (" (none on €13,000 or less)" if result.usc == 0 else "")
    )
    lines.append(
        f"- PRSI (Class A, 4.1%): {_money(result.prsi, symbol)}"
        + (" (none on €352 a week or less)" if result.prsi == 0 else "")
    )
    lines.append(f"- Total: {_money(result.total, symbol)}")
    lines.append(_per_year_line("Take-home", result.take_home, req, symbol))
    marginal = _marginal(lambda pay: ireland_tax(pay, filing_status=status).total, req.income)
    lines.append(_rates_line("ireland", result.effective_rate, marginal))

    extra = list(notes) + status_notes
    if result.prsi > 0:
        extra.append(_PRSI_NOTE)
    if req.age is not None and req.age >= 65:
        extra.append("Age credits and exemptions for people 65 and over aren't included.")
    if _PENSION.search(req.text):
        extra.append("Pension contributions aren't deducted.")
    return _finish(lines, extra)


def _netherlands_reply(req: "_Request", defaulted: bool, notes: List[str]) -> str:
    symbol = _SYMBOLS["netherlands"]
    result = netherlands_tax(req.income, thirty_percent_ruling=req.ruling)
    lines = [
        f"Dutch tax on {_income_phrase(req, symbol)}",
        _year_line("Tax year", NETHERLANDS_TAX_YEAR, defaulted),
        _assumptions([
            "salary only", "below State Pension (AOW) age",
            "30% ruling applied" if req.ruling else "no 30% ruling",
        ]),
    ]
    if req.ruling:
        lines.append(f"- 30% ruling: {_money(result.ruling_exemption, symbol)} tax-free")
    lines.append(f"- Box 1 income: {_money(result.box1_income, symbol)}")
    bands = _band_text(_band_split(result.box1_income, _DUTCH_BOX1_BRACKETS), symbol)
    lines.append(
        f"- Box 1 tax: {_money(result.box1_tax, symbol)}"
        + (f" ({bands}; includes national insurance contributions)" if bands else "")
    )
    detail = (
        f"general {_money(result.general_tax_credit, symbol)}, "
        f"labour {_money(result.labour_tax_credit, symbol)}"
    )
    if result.tax_credits < result.general_tax_credit + result.labour_tax_credit - 0.005:
        detail += ", limited to the tax"
    lines.append(f"- Less tax credits: {_money(result.tax_credits, symbol)} ({detail})")
    lines.append(f"- Total: {_money(result.total, symbol)}")
    lines.append(_per_year_line("Take-home", result.take_home, req, symbol))
    marginal = _marginal(
        lambda pay: netherlands_tax(pay, thirty_percent_ruling=req.ruling).total, req.income
    )
    lines.append(_rates_line("netherlands", result.effective_rate, marginal))

    extra = list(notes)
    if req.ruling:
        extra.append(
            "The 30% ruling is modelled as 30% of salary tax-free, on salary up to €246,000; "
            "its eligibility conditions aren't checked."
        )
    if _HOLIDAY.search(req.text):
        extra.append("Holiday allowance (vakantiegeld) is taxable; include it in the salary if it's paid on top.")
    if req.age is not None and req.age >= 67:
        extra.append(
            "From State Pension (AOW) age the first-bracket rate is lower; this uses the rates "
            "for people below it."
        )
    if _PENSION.search(req.text):
        extra.append("Pension contributions aren't deducted.")
    if _MARRIED.search(req.text):
        extra.append("Dutch tax is per person; sharing deductions with a tax partner isn't included.")
    return _finish(lines, extra)


def _singapore_reply(req: "_Request", defaulted: bool, notes: List[str]) -> str:
    symbol = _SYMBOLS["singapore"]
    band = singapore_age_band(req.age)
    result = singapore_tax(req.income, age_band=band, cpf_contributions=req.cpf)
    lines = [
        f"Singapore income tax on {_income_phrase(req, symbol)}",
        _year_line("Year of assessment", "YA 2025 (income earned in 2024)", defaulted),
        _assumptions([
            f"tax resident {_SINGAPORE_AGE_TEXT[band]}", "employment income only",
            "earned income and CPF relief" if req.cpf else "earned income relief only",
        ]),
    ]
    if result.total_reliefs >= SINGAPORE_RELIEF_CAP:
        basis = f"after reliefs, capped at {_money(SINGAPORE_RELIEF_CAP, symbol)}"
    elif req.cpf:
        basis = f"after {_money(result.total_reliefs, symbol)} of earned income and CPF relief"
    else:
        basis = f"after {_money(result.earned_income_relief, symbol)} earned income relief"
    lines.append(f"- Chargeable income: {_money(result.chargeable_income, symbol)} ({basis})")
    lines.append(f"- Income tax: {_money(result.income_tax, symbol)}")
    if result.rebate > 0:
        lines.append(f"- Less YA 2025 rebate (60%, up to S$200): {_money(result.rebate, symbol)}")
    lines.append(f"- Total: {_money(result.total, symbol)}")
    lines.append(
        _per_year_line("After income tax", result.after_tax, req, symbol, " (CPF contributions not deducted)")
    )
    marginal = _marginal(
        lambda pay: singapore_tax(pay, age_band=band, cpf_contributions=req.cpf).total, req.income
    )
    lines.append(_rates_line("singapore", result.effective_rate, marginal))

    extra = list(notes)
    if not req.cpf:
        extra.append('Employee CPF contributions also get relief; add them, e.g. "CPF of S$12,000".')
    return _finish(lines, extra)


def _scotland_reply(req: "_Request") -> str:
    symbol = _SYMBOLS["uk"]
    ni = uk_national_insurance(req.income)
    return _finish([
        "Scottish income tax isn't in tax-break's tables (Scotland sets its own bands and "
        "rates), so I can't estimate it.",
        f"National Insurance is UK-wide: on {_income_phrase(req, symbol)} it comes to "
        f"{_money(ni, symbol)} for {UK_TAX_YEAR} (8% from £12,570 to £50,270, 2% above).",
        "Ask about England, Wales or Northern Ireland for a full UK estimate.",
    ])


def _year_decline(country: str, asked: str) -> str:
    held, latest = _TABLES_HELD[country]
    return _finish(
        [
            f"tax-break has {held}, not {asked}, so I can't estimate that year.",
            f"Ask without a year to use {latest}, the latest it has.",
        ],
        disclaimer=False,
    )


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
                "tax-break covers employment (salary) income only, so I can't estimate tax on "
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
                "tax-break works forward from a gross (before-tax) salary, so I can't start from a "
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
# somewhere tax-break doesn't cover.
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
for _state in US_STATES.values():
    _register_places("us:" + _state.code, _state.name.lower())
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

_PLACES = re.compile(
    r"(?<![a-z])(?:"
    + "|".join(re.escape(name) for name in sorted(_PLACE_KINDS, key=len, reverse=True))
    + r")(?![a-z])"
)
_US_LOWER = re.compile(
    r"(?<!\bgive\s)(?<!\btell\s)(?<!\bshow\s)(?<!\bhelp\s)(?<!\blet\s)(?<!\bto\s)(?<!\bwith\s)"
    r"\bus\s+(?:federal\s+|income\s+|state\s+)*"
    r"(?:tax(?:es)?|take[- ]?home|salary|income|paycheck|net\s+pay)\b"
    r"|\b(?:in|from|for)\s+the\s+us\b"
)
_US_UPPER = re.compile(r"\bUS\b")
_US_STATE_CODE = re.compile(r"\b(?i:in|from|state\s+of)\s+(?P<code>[A-Z]{2})\b")


def _places(original: str) -> List[Tuple[int, str]]:
    """Every place named in the question, as (position, kind), in order."""

    lowered = original.lower()
    found = [(m.start(), _PLACE_KINDS[m.group()]) for m in _PLACES.finditer(lowered)]
    found += [(m.start(), "us") for m in _US_LOWER.finditer(lowered)]
    letters = [c for c in original if c.isalpha()]
    shouting = len(letters) >= 8 and sum(c.isupper() for c in letters) > 0.6 * len(letters)
    if not shouting:
        found += [(m.start(), "us") for m in _US_UPPER.finditer(original)]
        for m in _US_STATE_CODE.finditer(original):
            code = m.group("code")
            if code in US_STATES and code != "LA":
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
            f"tax-break covers {_COVERAGE}, so I can't estimate tax for {unsupported[0]}.",
        ])
    foreign = [a.currency[2:] for a in amounts if a.currency and a.currency.startswith("x:")]
    if foreign:
        raise _ask([
            f"tax-break covers {_COVERAGE}, so I can't estimate tax on a salary in {foreign[0]}.",
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
        f"Which country is the salary of {shown} for? tax-break covers {_COVERAGE}.",
        f'Ask e.g. "UK tax on {shown}" or "tax on {shown} in India".',
    ])


def _check_currencies(country: str, amounts: Sequence[_Amount], notes: List[str]) -> None:
    """Refuse amounts in another country's currency; tax-break doesn't convert."""

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
                f"tax-break works from a yearly salary, so I need more than {shown}. Give the "
                f'hours you work a week, e.g. "{example}", or a yearly, monthly or weekly salary.',
            ])
        annual = value * hours * 52
        notes.append(f"I took {shown} for {hours:g} hours a week as {_money(annual, symbol)} a year.")
        return annual, annual, "year"
    if period == "day":
        raise _ask([
            "tax-break works from a yearly salary; give a yearly, monthly or weekly figure rather "
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


def _year_choice(
    country: str, kind: str, first: int, second: Optional[int]
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Read one year mention as (key, note, None), or (None, None, label) if it isn't held."""

    span = f"{first}-{second % 100:02d}" if second is not None else None
    if country == "india":
        note = None
        if second is not None:
            start = first - 1 if kind in ("ay", "ya") else first
            if second != first + 1:
                return None, None, f"FY {span}"
        elif kind == "fy":
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
        label = f"{start}-{(start + 1) % 100:02d}"
        key = "FY" + label
        return (key, note, None) if key in INDIA_YEARS else (None, None, "FY " + label)
    if country == "uk":
        if second is not None:
            return ("2025/26", None, None) if (first, second) == (2025, 2026) else (
                None, None, f"{first}/{second % 100:02d}"
            )
        if first == 2025:
            return "2025/26", "I took 2025 as the 2025/26 tax year (6 April 2025 to 5 April 2026).", None
        return None, None, str(first)
    if country == "singapore":
        if kind == "ya":
            return ("YA 2025", None, None) if first == 2025 and second is None else (
                None, None, f"YA {span or first}"
            )
        if second is not None:
            return None, None, span
        if first == 2024:
            return "YA 2025", "I took 2024 income as YA 2025.", None
        if first == 2025:
            return "YA 2025", "tax-break has YA 2025 (income earned in 2024) only, so I used that.", None
        return None, None, str(first)
    if second is None and first == 2025:
        return "2025", None, None
    return None, None, span or str(first)


def _resolve_year(country: str, facts: _Facts) -> Tuple[Optional[str], bool, List[str]]:
    """Return the India year key (None elsewhere), whether it was defaulted, and notes."""

    if not facts.years:
        return (LATEST_INDIA_FY if country == "india" else None), True, []
    years = sorted(facts.years)
    key, note, declined = _year_choice(country, *years[0][1:])
    if declined:
        raise _Reply(_year_decline(country, declined))
    notes = [note] if note else []
    if any(_year_choice(country, *year[1:])[0] != key for year in years[1:]):
        label = INDIA_YEARS[key].label if country == "india" else key
        notes.append(f"I used {label}, the first year given.")
    return (key if country == "india" else None), False, notes


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
                '"home loan interest 2 lakh", or principal (80C).'
            )
        else:
            hint = ""
            if country == "india" and keyword in ("deduction", "deductions"):
                hint = '; name the section, e.g. "80C 1.5 lakh"'
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
    places = _places(original)

    try:
        country, notes = _decide(places, amounts, salary, low)
        if salary is None:
            return _no_salary(amounts, country)
        if country is None:
            return None
        symbol = _SYMBOLS[country]
        _check_currencies(country, amounts, notes)

        kinds = [kind for _, kind in places]
        scotland = False
        if country == "uk" and "scotland" in kinds:
            if "ewni" in kinds:
                notes.append(
                    "Scottish income tax isn't in tax-break, so I used the rates for England, "
                    "Wales and Northern Ireland."
                )
            else:
                scotland = True
        state: Optional[str] = None
        if country == "us":
            codes = list(dict.fromkeys(kind[3:] for kind in kinds if kind.startswith("us:")))
            if codes:
                state = codes[0]
                if len(codes) > 1:
                    notes.append(f"I used {US_STATES[state].name} for state tax, the first state given.")

        annual, stated, period = _salary_per_year(salary, facts, symbol, notes)
        if len(salaries) > 1:
            others = " or ".join(_describe(other, symbol) for other in salaries[1:])
            notes.append(
                f"I used {_describe(salary, symbol)}, the first salary given; ask again for {others}."
            )
        fy, defaulted, year_notes = _resolve_year(country, facts)
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
            return _india_reply(req, fy or LATEST_INDIA_FY, defaulted, notes)
        if country == "uk":
            return _scotland_reply(req) if scotland else _uk_reply(req, defaulted, notes)
        if country == "us":
            return _us_reply(req, state, defaulted, notes)
        if country == "ireland":
            return _ireland_reply(req, defaulted, notes)
        if country == "netherlands":
            return _netherlands_reply(req, defaulted, notes)
        return _singapore_reply(req, defaulted, notes)
    except _Reply as reply:
        return reply.reply


def estimate(text: str) -> Optional[str]:
    """Answer a salary tax question with tax-break's tables, or None if it isn't one."""

    if not text or len(text) > _MAX_TEXT:
        return None
    try:
        return _estimate(text)
    except (ArithmeticError, ValueError):
        return None


def usage() -> str:
    examples = "; ".join(f'"{example}"' for example in _EXAMPLES.values())
    return _finish([
        "I can estimate income tax and take-home pay on a salary, using tax-break's tables.",
        f"It covers {_COVERAGE}.",
        f"Try: {examples}.",
        'Add details such as "a month", a bonus, "old regime", "FY 2024-25", "80C 1.5 lakh", '
        '"student loan plan 2", "married with 2 kids", a US state or "30% ruling".',
    ])
