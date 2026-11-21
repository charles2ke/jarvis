import math
import re
import unittest

from jarvis import tax


class EngineTests(unittest.TestCase):
    # Golden figures cross-checked against tax-break's compiled TypeScript engine.

    def test_india_regimes_rebate_and_marginal_relief(self):
        comparison = tax.india_compare(1500000)
        self.assertEqual((comparison.new.total, comparison.old.total), (97500, 257400))
        self.assertEqual(comparison.recommended, "new")
        self.assertEqual(tax.india_tax(1275000).total, 0)
        self.assertEqual(tax.india_tax(1280000).total, 5200)

    def test_india_old_regime_caps_deductions_and_adds_surcharge(self):
        claims = tax.IndiaDeductions(section_80c=math.inf, section_80ccd1b=math.inf)
        old = tax.india_tax(2000000, regime="old", deductions=claims)
        self.assertEqual((old.section_80c, old.section_80ccd1b, old.total), (150000, 50000, 351000))
        self.assertEqual(tax.india_tax(10000000, regime="old", fy="FY2024-25").total, 3200340)

    def test_uk(self):
        result = tax.uk_tax(50000)
        self.assertEqual((result.income_tax, result.national_insurance), (7486, 2994.4))
        self.assertEqual(tax.uk_tax(40000, student_loan_plan="plan2").student_loan, 1038)
        self.assertEqual(tax.uk_tax(110000).personal_allowance, 7570)

    def test_us(self):
        result = tax.us_tax(85000, state="CA")
        self.assertEqual(
            (result.federal_income_tax, result.state.tax, result.take_home), (10149, 3916.7, 64431.8)
        )
        family = tax.us_tax(100000, filing_status="married_joint", children=2)
        self.assertEqual((family.child_tax_credit, family.take_home), (4400, 89007))

    def test_ireland_netherlands_and_singapore(self):
        self.assertEqual(tax.ireland_tax(60000).take_home, 44994)
        self.assertEqual(tax.netherlands_tax(70000, thirty_percent_ruling=True).take_home, 59248.9)
        self.assertEqual(tax.singapore_tax(120000).total, 7635)


class EstimateTests(unittest.TestCase):
    def assertReply(self, text, *fragments):
        reply = tax.estimate(text)
        self.assertIsNotNone(reply, text)
        for fragment in fragments:
            self.assertIn(fragment, reply, f"{text!r}:\n{reply}")
        return reply

    def test_reads_country_amount_and_period(self):
        cases = {
            "income tax on 15 lakh in India": ("₹15,00,000 a year", "₹97,500", "₹2,57,400"),
            "how much tax do I pay on £50,000": ("UK tax on £50,000 a year", "£39,519.60"),
            "tax on $85,000 in California": ("a year in California", "$64,431.80"),
            "net salary for 60000 euros in Ireland": ("€44,994",),
            "dutch tax on 70000 with 30% ruling": ("€59,248.90",),
            "singapore income tax on S$120,000": ("S$112,365",),
            "take-home pay on £3,000 a month": ("£3,000 a month (£36,000 a year)",),
            "in-hand salary for 12 lpa": ("₹12,00,000 a year",),
            "tax on £2,000 a fortnight": ("£52,000 a year",),
            "take home on £15 an hour 40 hours a week": ("£31,200 a year",),
            "UK tax on £50,000 plus a £5,000 bonus": ("£55,000 in all",),
            "salary 50000 bonus 5000 uk tax": ("£55,000 in all",),
            "UK take home on £40,000 student loan plan 2": ("Student loan (Plan 2): £1,038",),
        }
        for text, fragments in cases.items():
            with self.subTest(text=text):
                self.assertReply(text, *fragments)

    def test_replies_carry_the_disclaimer_and_credit(self):
        reply = self.assertReply("uk take home pay on 45000", tax.DISCLAIMER, tax.CREDIT)
        self.assertIn("2025/26", reply)

    def test_india_deductions(self):
        self.assertReply("income tax on 15 lakh 80c 1.5 lakh", "₹2,10,600")
        self.assertReply("income tax on 15 lakh, 80D for parents over 60: 50000", "₹2,41,800")
        self.assertReply("tax on 15 lakh, home loan interest 2 lakh, old regime", "₹1,95,000")
        self.assertReply(
            "tax on 20 lakh max 80c and nps",
            "80C ₹1,50,000 (the maximum), NPS 80CCD(1B) ₹50,000 (the maximum)",
            "₹3,51,000",
        )
        self.assertReply("tax on 15 lakh, home loan 2 lakh", "say whether it's interest (24(b))")
        self.assertReply("UK tax on 50k, max 80c and nps", "they're Indian deductions")

    def test_years(self):
        self.assertReply(
            "fy 2025 tax on 10 lakh",
            "I took FY 2025 as FY 2024-25",
            "the July 2024 Budget changed them",
        )
        self.assertReply("tax on 1 crore old regime FY 2024-25", "₹32,00,340")
        self.assertReply("uk tax 2025 on £60,000", "I took 2025 as the 2025/26 tax year")
        self.assertReply("uk tax in 1980 on £30,000", "not 1980")
        self.assertReply("income tax in the 2020s on £50,000", "UK tax on £50,000 a year")

    def test_us_filing_status_and_state(self):
        self.assertReply("joint tax return 150000 usa", "married filing jointly")
        self.assertReply("US tax on 90000 separate tax return", "married filing separately")
        self.assertReply("salary after tax 100k usa married 2 kids", "married filing jointly", "$89,007")
        self.assertReply("tax on $90,000 in Seattle", "a year in Washington")
        self.assertReply("tax on $120,000 in New York and New Jersey", "I used New York for state tax")
        self.assertReply("single mom US tax on 45000 with 2 kids", "head of household")

    def test_asks_or_declines_instead_of_guessing(self):
        cases = {
            "how much tax on 50000": "Which country is the salary of 50,000 for?",
            "tax on €60,000": "Ireland or the Netherlands?",
            "tax on CAD 80,000": "Canadian dollars",
            "income tax in Toronto on 80000": "tax for Canada",
            "UK tax on 50,000 CAD": "I don't convert currencies",
            "I earn 40k in Scotland, how much tax": "Scottish income tax isn't in tax-break's tables",
            "income tax 2023 uk 50000": "not 2023",
            "tax on 10 lakh fy 2019-20": "not FY 2019-20",
            "how much do I need to earn to take home £3,000 a month": "gross (before-tax)",
            "self-employed tax on £40,000": "employment (salary) income only",
            "take home on £15 an hour": "hours you work a week",
            "tax on 80c 1.5 lakh": "I need a gross salary",
        }
        for text, fragment in cases.items():
            with self.subTest(text=text):
                self.assertReply(text, fragment)

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
                self.assertIsNone(tax.estimate(text))

    def test_usage_examples_all_work(self):
        examples = re.findall(r'"([^"]+)"', tax.usage().splitlines()[2])
        self.assertEqual(len(examples), 6)
        for example in examples:
            with self.subTest(example=example):
                self.assertReply(example, tax.CREDIT)


if __name__ == "__main__":
    unittest.main()
