import re
import unittest

from project_support import ProjectTestCase, fake_project, missing_projects

from jarvis import projects, tax
from jarvis.tax import CREDIT, DISCLAIMER, estimate, usage

# Made-up answers in the shapes bridges/tax-break.mjs returns. The years, the
# states and every figure are invented (flat percentages and round limits):
# these tests are about how Jarvis reads a request, what it asks tax-break for
# and how it words the reply, not about anyone's tax rules.
META = {
    "years": [
        {"key": "FY2030-31", "label": "FY 2030-31 (sample)"},
        {"key": "FY2031-32", "label": "FY 2031-32 (sample)"},
    ],
    "states": [
        {"code": "CA", "name": "California"},
        {"code": "TX", "name": "Texas"},
        {"code": "WA", "name": "Washington"},
        {"code": "ZQ", "name": "Zephyr Quay"},
    ],
    "countries": [{"value": "uk", "tagline": "A sample UK calculator."}],
}


def _international(payload):
    results = []
    for data in payload["inputs"]:
        income = data["annualIncome"] + data.get("bonus", 0)
        tax_due, charge = income / 10, income / 20
        loan = 300 if data.get("studentLoanPlan") else 0
        state_tax = income / 50 if data.get("state") else 0
        cliff = 2000 if income > 100_000 else 0
        total = tax_due + charge + loan + state_tax + cliff
        detail = {
            "netIncome": income - total,
            "personalAllowance": 1000, "nationalInsurance": charge, "studentLoanRepayment": loan,
            "ficaTax": charge, "additionalMedicareTax": 0, "childTaxCredit": 0,
            "standardRateCutOff": 30000, "universalSocialCharge": charge, "prsi": 0,
            "thirtyPercentExemption": 0, "box1Income": income, "box1Tax": tax_due + charge,
            "generalTaxCredit": 0, "labourTaxCredit": 0,
            "earnedIncomeRelief": 1000, "totalReliefsBeforeCap": 1000, "totalReliefsAllowed": 1000,
            "chargeableIncome": income - 1000, "taxRebate": 0,
        }
        results.append({
            "country": data["country"], "standardDeduction": 1000,
            "taxableIncome": income - 1000, "incomeTax": tax_due + cliff, "taxCredits": 0,
            "totalTaxLiability": total, "state": data.get("state"), "stateTax": state_tax,
            "stateTaxableIncome": income - 1000, data["country"]: detail,
        })
    return results


def _capped(claim, limit):
    return limit if claim == "max" else min(claim, limit)


def _regime(data, regime):
    old = regime == "old"
    salary = data["salary"]["basic"] + data["salary"]["otherTaxableAllowances"]
    claims = data.get("deductions", {}) if old else {}
    set_off = _capped(data.get("houseProperty", {}).get("homeLoanInterest", 0), 30_000) if old else 0
    standard = 5_000 if old else 10_000
    breakdown = {
        "section80C": _capped(claims.get("section80C", 0), 20_000), "section80D": 0,
        "section80CCD1B": 0, "section80E": 0,
        "section80G": claims.get("section80G", 0), "standardDeduction": standard,
    }
    deductions = sum(breakdown.values())
    taxable = max(salary - set_off - deductions, 0)
    tax_due = taxable * (0.2 if old else 0.1)
    return {
        "taxableSalaryIncome": salary, "grossTotalIncome": salary - set_off,
        "totalDeductions": deductions, "deductionsBreakdown": breakdown,
        "taxableIncome": taxable, "taxBeforeRebate": tax_due, "rebate": 0,
        "surcharge": 0, "marginalRelief": 0, "cess": 0, "totalTaxLiability": tax_due,
    }


def _india(payload):
    results = []
    for data in payload["inputs"]:
        new, old = _regime(data, "new"), _regime(data, "old")
        cheaper = "new" if new["totalTaxLiability"] <= old["totalTaxLiability"] else "old"
        savings = abs(new["totalTaxLiability"] - old["totalTaxLiability"])
        results.append({"new": new, "old": old, "recommendedRegime": cheaper, "savings": savings})
    return results


ENGINE = {"meta": META, "india": _india, "international": _international}


class FakeEngineTestCase(unittest.TestCase):
    def setUp(self):
        tax._meta.cache_clear()
        self.addCleanup(tax._meta.cache_clear)
        faked = fake_project("tax-break", ENGINE)
        self.calls = faked.__enter__()
        self.addCleanup(faked.__exit__, None, None, None)

    def reply(self, text, *fragments):
        reply = estimate(text)
        self.assertIsNotNone(reply, text)
        for fragment in fragments:
            self.assertIn(fragment, reply, f"{text!r}:\n{reply}")
        return reply

    def inputs(self, action):
        """The inputs Jarvis last sent with ``action``."""

        return [payload for name, payload in self.calls if name == action][-1]["inputs"]


class EstimateTests(FakeEngineTestCase):
    def test_uk_reply_shows_the_engines_figures(self):
        reply = self.reply("UK take-home on £20,000")
        self.assertEqual(self.calls, [
            ("meta", None),
            ("international", {"inputs": [
                {"country": "uk", "annualIncome": 20000.0},
                {"country": "uk", "annualIncome": 21000.0},
            ]}),
        ])
        self.assertEqual(reply.splitlines(), [
            "UK tax on £20,000 a year",
            'Calculator: tax-break for the UK — "A sample UK calculator."',
            "Assumptions: England, Wales or Northern Ireland rates, salary only, no student loan, "
            "no pension contributions.",
            "- Personal allowance: £1,000",
            "- Taxable income: £19,000",
            "- Income tax: £2,000",
            "- National Insurance: £1,000",
            "- Total: £3,000",
            "- Take-home: £17,000 a year, about £1,417 a month",
            "- Rates: 15% effective, 15% marginal on the next £1,000",
            DISCLAIMER,
            CREDIT,
        ])

    def test_one_engine_run_per_reply_and_one_meta_read(self):
        self.reply("UK tax on £20,000")
        self.reply("tax on $50,000 in Texas")
        self.assertEqual([name for name, _ in self.calls], ["meta", "international", "international"])

    def test_a_jump_in_tax_is_flagged(self):
        self.reply("UK tax on £99,500", "marginal on the next £1,000 (a threshold is crossed here")
        self.assertNotIn("threshold", self.reply("UK tax on £50,000"))

    def test_reads_country_amount_and_period(self):
        cases = {
            "income tax on 15 lakh in India": "Indian income tax on ₹15,00,000 a year",
            "how much tax do I pay on £50,000": "UK tax on £50,000 a year",
            "tax on $85,000 in California": "US tax on $85,000 a year in California",
            "net salary for 60000 euros in Ireland": "Irish tax on €60,000 a year",
            "dutch tax on 70000 with 30% ruling": "Dutch tax on €70,000 a year",
            "singapore income tax on S$120,000": "Singapore income tax on S$120,000 a year",
            "take-home pay on £3,000 a month": "UK tax on £3,000 a month (£36,000 a year)",
            "in-hand salary for 12 lpa": "Indian income tax on ₹12,00,000 a year",
            "tax on £2,000 a fortnight": "UK tax on £52,000 a year",
            "take home on £15 an hour 40 hours a week": "UK tax on £31,200 a year",
            "UK tax on £50,000 plus a £5,000 bonus": "plus a £5,000 bonus (£55,000 in all)",
            "salary 50000 bonus 5000 uk tax": "plus a £5,000 bonus (£55,000 in all)",
        }
        for text, title in cases.items():
            with self.subTest(text=text):
                self.assertIn(title, self.reply(text).splitlines()[0])
        self.assertEqual(self.inputs("international")[0]["bonus"], 5000)

    def test_salary_signs_around_currency_are_preserved(self):
        for text in (
            "UK tax on -£50,000",
            "UK tax on £-50,000",
            "UK tax on -+£50,000",
            "UK tax on £-+50,000",
            "UK tax on £0",
        ):
            with self.subTest(text=text):
                self.assertIsNone(estimate(text))
                self.assertEqual(self.calls, [])

        for text in ("UK tax on +£50,000", "UK tax on £+50,000"):
            with self.subTest(text=text):
                self.reply(text)
                self.assertEqual(self.inputs("international")[0]["annualIncome"], 50_000)

    def test_details_become_engine_options(self):
        cases = {
            "UK tax on £40,000 with student loan plan 2": {"studentLoanPlan": "plan2"},
            "UK tax on £40,000 with a plan 3 student loan": {"studentLoanPlan": "postgraduate"},
            "joint tax return 150000 usa": {"filingStatus": "marriedJoint"},
            "US tax on 90000 separate tax return": {"filingStatus": "marriedSeparate"},
            "US tax on $60,000 head of household": {"filingStatus": "headOfHousehold"},
            "salary after tax 100k usa married 2 kids": {
                "filingStatus": "marriedJoint", "dependentsUnder17": 2,
            },
            "Irish tax on €40,000, married": {"filingStatus": "marriedOneIncome"},
            "Irish tax on €40,000 as a single parent": {"filingStatus": "singleParent"},
            "dutch tax on 70000 with 30% ruling": {"thirtyPercentRuling": True},
            "Singapore tax on S$90,000 with CPF of S$10,000, I'm 57": {
                "ageBand": "55to59", "reliefs": {"cpfContributions": 10000},
            },
        }
        for text, options in cases.items():
            with self.subTest(text=text):
                self.reply(text)
                first, more = self.inputs("international")
                self.assertEqual({key: first.get(key) for key in options}, options)
                self.assertEqual(more["annualIncome"], first["annualIncome"] + 1000)
        self.reply("UK tax on £40,000 with student loan plan 2", "- Student loan (Plan 2): £300")
        self.reply("UK tax on £40,000, plan 3 loan", "I took Plan 3 as the Postgraduate Loan.")
        self.reply("salary after tax 100k usa married 2 kids", 'say "filing separately" if not')
        self.reply("single mom US tax on 45000 with 2 kids", '"head of household"')
        self.reply("Dutch tax on €50,000, I'm 70", "tax-break's Dutch calculator doesn't take an age")

    def test_us_states_come_from_the_project(self):
        cases = {
            "tax on $50,000 in California": "CA",
            "tax on $50,000 in TX": "TX",
            "tax on $90,000 in Seattle": "WA",
            "tax on $50,000 in Zephyr Quay": "ZQ",
            "tax on $50,000 in ZZ": None,
            "tax on $50,000 in NYC": None,
        }
        for text, code in cases.items():
            with self.subTest(text=text):
                self.reply(text)
                self.assertEqual(self.inputs("international")[0].get("state"), code)
        self.reply(
            "tax on $50,000 in California",
            "US tax on $50,000 a year in California",
            "- California income tax: $1,000 (on $49,000 of state taxable income)",
        )
        self.reply("tax on $50,000 in NYC", "tax-break has no state tax figures for the place you named")
        self.reply("tax on $50,000 in ZZ", 'Add a state for state income tax, e.g. "in California".')
        self.reply("tax on $120,000 in California and Texas", "I used California for state tax")
        self.assertNotIn("Calculator:", self.reply("tax on $50,000 in Texas"))

    def test_a_state_figure_that_ignores_the_filing_status_is_noted(self):
        text = "tax on $90,000 in California, married filing jointly"
        note = "tax-break's California figure is the same as a single filer's"
        self.reply(text, note, "a married filing jointly return there may differ")
        self.assertEqual([data["filingStatus"] for data in self.inputs("international")],
                         ["marriedJoint", "marriedJoint", "single"])
        self.assertNotIn(note, self.reply("tax on $90,000 in California"))
        self.assertEqual(len(self.inputs("international")), 2)

        def by_status(payload):
            results = _international(payload)
            for data, result in zip(payload["inputs"], results):
                if data["filingStatus"] != "single":
                    result["stateTax"] /= 2
            return results

        with fake_project("tax-break", dict(ENGINE, international=by_status)):
            self.assertNotIn(note, estimate(text))

    def test_scotland_gets_national_insurance_only(self):
        reply = self.reply("I earn £40,000 in Scotland, how much tax")
        self.assertTrue(reply.startswith("Scotland sets its own income tax bands and rates"))
        self.assertIn("tax-break puts it at £2,000", reply)
        self.assertEqual(len(self.inputs("international")), 1)
        self.reply(
            "tax on £45,000 in Scotland and England",
            "UK tax on £45,000 a year",
            "I can't do Scottish income tax with tax-break",
        )


class IndiaTests(FakeEngineTestCase):
    def test_both_regimes_for_the_latest_year(self):
        reply = self.reply(
            "income tax on 5 lakh in India",
            "Financial year: FY 2031-32 (sample), the latest in tax-break's tables.",
            "New regime:", "Old regime:", "- Total tax: ₹49,000", "- Total tax: ₹99,000",
            "The new regime is lower by ₹50,000 a year.",
        )
        self.assertIn("would lower the old figure", reply)
        first, more = self.inputs("india")
        self.assertEqual((first["assessmentYear"], first["ageCategory"]), ("FY2031-32", "below60"))
        self.assertEqual((first["salary"]["basic"], more["salary"]["basic"]), (500000, 501000))
        self.assertNotIn("deductions", first)

    def test_deductions_and_full_claims(self):
        self.reply(
            "income tax on 5 lakh, old regime, max 80c, 80G donation of 3000 and home loan "
            "interest 50000",
            "- Home-loan interest 24(b): ₹30,000 set off against salary (capped from ₹50,000)",
            "- Deductions: standard ₹5,000, 80C ₹20,000 (the maximum), 80G ₹3,000",
            "- Taxable income: ₹4,42,000 (after ₹28,000 of deductions)",
            "For comparison, the new regime comes to ₹49,000.",
            "tax-break deducted the whole 80G donation",
        )
        first = self.inputs("india")[0]
        self.assertEqual(first["deductions"]["section80C"], "max")
        self.assertEqual(first["deductions"]["section80G"], 3000)
        self.assertEqual(first["houseProperty"], {"type": "self-occupied", "homeLoanInterest": 50000})

    def test_claims_the_new_regime_leaves_unused(self):
        self.reply("income tax on 5 lakh, 80c 1 lakh, new regime", "uses none of the deductions you gave")
        self.reply("tax on 15 lakh, home loan 1.8 lakh", "say whether it's interest (24(b))")
        self.reply("UK tax on 50k, max 80c and nps", "they're Indian deductions")
        self.reply("income tax on 15 lakh, 80D for parents over 60: 40000")
        claims = self.inputs("india")[0]["deductions"]["section80D"]
        self.assertEqual((claims["parentsPremium"], claims["parentsSenior"]), (40000, True))

    def test_years_come_from_the_project(self):
        cases = {
            "income tax on 5 lakh fy 2030-31": ("FY2030-31", "Financial year: FY 2030-31 (sample)."),
            "fy 2031 tax on 10 lakh": ("FY2030-31", "I took FY 2031 as FY 2030-31"),
            "tax on 10 lakh AY 2032-33": ("FY2031-32", "Financial year: FY 2031-32 (sample)."),
            "tax on 10 lakh for FY 2030-31 and FY 2031-32": ("FY2030-31", "the first year given"),
        }
        for text, (key, fragment) in cases.items():
            with self.subTest(text=text):
                self.reply(text, fragment)
                self.assertEqual(self.inputs("india")[0]["assessmentYear"], key)

    def test_a_year_the_project_lacks_is_declined(self):
        reply = self.reply("tax on 10 lakh fy 2019-20")
        self.assertEqual(reply.splitlines(), [
            "tax-break has Indian tables for FY 2030-31 to FY 2031-32, not FY 2019-20, so I can't "
            "estimate that year.",
            "Ask without a year to use FY 2031-32 (sample), the latest it has.",
            CREDIT,
        ])
        self.assertEqual(self.calls, [("meta", None)])


class RequestTests(FakeEngineTestCase):
    def test_other_countries_note_an_asked_year(self):
        self.reply("uk tax 2025 on £60,000", "You asked about 2025, but tax-break's calculator for the UK")
        self.assertEqual(set(self.inputs("international")[0]), {"country", "annualIncome"})
        self.reply("Singapore tax on S$90,000 for YA 2024", "You asked about YA 2024")
        self.assertNotIn("You asked", self.reply("income tax in the 2020s on £50,000"))

    def test_asks_or_declines_instead_of_guessing(self):
        cases = {
            "how much tax on 50000": "Which country is the salary of 50,000 for?",
            "tax on €60,000": "Ireland or the Netherlands?",
            "tax on CAD 80,000": "Canadian dollars",
            "income tax in Toronto on 80000": "so I can't estimate tax for Canada",
            "UK tax on 50,000 CAD": "I don't convert currencies",
            "take home on £15 an hour": "hours you work a week",
            "tax on 80c 1 lakh": "I need a gross salary",
        }
        for text, fragment in cases.items():
            with self.subTest(text=text):
                self.assertTrue(self.reply(text, fragment).endswith(CREDIT))
        self.assertEqual({name for name, _ in self.calls}, {"meta"})

    def test_requests_it_cant_take_need_no_project(self):
        cases = {
            "self-employed tax on £40,000": "on a salary (employment income)",
            "how much do I need to earn to take home £3,000 a month": "gross (before-tax)",
        }
        for text, fragment in cases.items():
            with self.subTest(text=text):
                self.reply(text, fragment)
        self.assertEqual(self.calls, [])

    def test_leaves_other_questions_to_other_skills(self):
        for text in (
            "",
            "what is income tax",
            "income tax 2025",
            "taxes in 1950",
            "tax evasion in the 1920s",
            "tax on 1000s of pounds in the uk",
            "20% tax on 500",
            "how much is 50000 after 25% tax",
            "how much is 15% sales tax on $80",
            "VAT on £120",
            "calculate GST on 5000 rupees",
            "capital gains tax on 10000",
            "inheritance tax on £500,000",
            "budget for 3000 after tax",
            "what's 30% of 70000",
            "paid 5000 in taxes",
            "add a note: pay income tax of £5,000",
            "I'm worried about paying my taxes",
            "UK tax on £50,000 " + "x" * 1000,
        ):
            with self.subTest(text=text[:60]):
                self.assertIsNone(estimate(text))
        self.assertEqual(self.calls, [])

    def test_usage_examples_all_work(self):
        examples = re.findall(r'"([^"]+)"', usage().splitlines()[2])
        self.assertEqual(len(examples), 6)
        for example in examples:
            with self.subTest(example=example):
                self.assertTrue(self.reply(example).endswith(CREDIT))


class TaxProjectProblemTests(unittest.TestCase):
    def setUp(self):
        tax._meta.cache_clear()
        self.addCleanup(tax._meta.cache_clear)

    def test_missing_project_explains_the_setup(self):
        with missing_projects():
            self.assertIsNone(estimate("what is income tax"))
            self.assertIn("with tax-break's tax engine", usage())
            self.assertNotRegex(usage(), r"\b(?:19|20)\d\d\b")
            with self.assertRaises(projects.ProjectUnavailable) as raised:
                estimate("UK take-home on £50,000")
        self.assertIn("git submodule update --init projects/tax-break", str(raised.exception))
        self.assertIn("https://charles2ke.github.io/tax-break/", str(raised.exception))

    def test_unexpected_answers_are_errors(self):
        def engine(**changes):
            return dict(ENGINE, **changes)

        broken = {
            "no years": engine(meta=dict(META, years=[])),
            "odd year key": engine(meta=dict(META, years=[{"key": "2031", "label": "2031"}])),
            "odd state code": engine(meta=dict(META, states=[{"code": "Texas", "name": "Texas"}])),
            "no meta": engine(meta=None),
            "too few results": engine(international=lambda payload: _international(payload)[:1]),
            "wrong country": engine(
                international=lambda payload: [dict(r, country="us") for r in _international(payload)]
            ),
            "missing figure": engine(
                international=lambda payload: [dict(r, incomeTax=None) for r in _international(payload)]
            ),
        }
        for name, actions in broken.items():
            tax._meta.cache_clear()
            with self.subTest(name), fake_project("tax-break", actions):
                with self.assertRaises(projects.ProjectError):
                    estimate("UK tax on £20,000")
        tax._meta.cache_clear()
        no_old = engine(india=lambda payload: [dict(r, old=None) for r in _india(payload)])
        with fake_project("tax-break", no_old), self.assertRaises(projects.ProjectError):
            estimate("income tax on 5 lakh in India")


class TaxProjectTests(ProjectTestCase):
    """Runs tax-break's own engine from projects/tax-break with Node.js."""

    project = "tax-break"

    def setUp(self):
        tax._meta.cache_clear()
        self.addCleanup(tax._meta.cache_clear)

    def test_known_estimates(self):
        # tax-break's figures for these salaries; the website demo asks the first.
        cases = {
            "UK take-home on £50,000": (
                "- Income tax: £7,486", "- National Insurance: £2,994.40", "- Total: £10,480.40",
                "- Take-home: £39,519.60 a year",
            ),
            "income tax on 15 lakh in India": ("- Total tax: ₹97,500", "- Total tax: ₹2,57,400"),
            "tax on $85,000 in California": ("a year in California", "- Take-home: $64,431.80 a year"),
        }
        for text, fragments in cases.items():
            with self.subTest(text=text):
                reply = estimate(text)
                for fragment in fragments:
                    self.assertIn(fragment, reply)

    def test_every_country_and_detail(self):
        for text in (
            "UK tax on £40,000 with student loan plan 2 and a £2,000 bonus",
            "US tax on $100,000 married filing jointly with 2 kids in New York",
            "US tax on $300,000",
            "Irish tax on €60,000, married",
            "Dutch tax on €70,000 with the 30% ruling",
            "Singapore tax on S$120,000 with CPF of S$20,000",
            "income tax on 20 lakh, old regime, max 80c, 80G donation of 10000 and home loan "
            "interest 3 lakh",
            "income tax on 60 lakh new regime",
            "take home on ₹1,00,000 a month",
        ):
            with self.subTest(text=text):
                reply = estimate(text)
                lines = reply.splitlines()
                self.assertEqual(lines[-2:], [DISCLAIMER, CREDIT])
                self.assertTrue(any(line.startswith("- Rates: ") for line in lines))
                self.assertNotRegex(reply, r"\bnan\b|\bNone\b|Infinity")

    def test_what_the_engine_cant_do_gets_an_honest_reply(self):
        reply = estimate("I earn £40,000 in Scotland, how much tax")
        self.assertIn("can't estimate Scottish income tax", reply)
        self.assertRegex(reply, r"tax-break puts it at £[\d,.]+\.")
        self.assertIn("You asked about 2023/24", estimate("UK tax in 2023/24 on £30,000"))

    def test_indian_years_come_from_the_project(self):
        meta = tax._meta()
        for key, label in meta.years:
            with self.subTest(year=key):
                self.assertIn(f"Financial year: {label}", estimate(f"income tax on 12 lakh for FY {key[2:]}"))
        start = int(min(key for key, _ in meta.years)[2:6]) - 1
        reply = estimate(f"income tax on 12 lakh for FY {start}-{(start + 1) % 100:02d}")
        self.assertTrue(reply.startswith("tax-break has Indian tables for FY "))

    def test_every_us_state_is_recognised(self):
        meta = tax._meta()
        for code, name in meta.states:
            with self.subTest(state=name):
                kinds = [kind for _, kind in tax._places(f"tax on $80,000 in {name}", meta.states)]
                self.assertEqual(kinds, ["us:" + code])


if __name__ == "__main__":
    unittest.main()
