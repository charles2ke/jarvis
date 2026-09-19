import unittest

from jarvis import finance
from jarvis.assistant import Assistant


class FinanceGlossaryTests(unittest.TestCase):
    def test_lookup_by_title_and_alias(self):
        self.assertEqual(finance.lookup("Inflation").title, "Inflation")
        self.assertEqual(finance.lookup("gross domestic product").title, "GDP")
        self.assertEqual(finance.lookup("etf").title, "Index funds and ETFs")
        self.assertEqual(finance.lookup("401k").title, "Retirement saving")

    def test_lookup_is_forgiving(self):
        self.assertEqual(finance.lookup("  Recession! ").title, "Recession")
        self.assertEqual(finance.lookup("the economy").title, "Economics")
        self.assertEqual(finance.lookup("inflaton").title, "Inflation")

    def test_lookup_unknown_returns_none(self):
        self.assertIsNone(finance.lookup("quantum tulip futures"))
        self.assertIsNone(finance.lookup(""))

    def test_topics_are_sorted_titles(self):
        titles = finance.topics()
        self.assertEqual(titles, sorted(titles))
        self.assertIn("Compound interest", titles)
        self.assertEqual(len(titles), len(finance.ENTRIES))

    def test_suggestions_offer_close_titles(self):
        self.assertIn("Recession", finance.suggestions("recesion"))
        self.assertEqual(finance.suggestions(""), [])


class MoneyMathTests(unittest.TestCase):
    def test_compound_interest_with_contributions(self):
        self.assertAlmostEqual(
            finance.compound_interest(1000, 0.0, 2), 1000.0, places=6
        )
        self.assertAlmostEqual(
            finance.compound_interest(0, 0.0, 1, contribution=100), 1200.0, places=6
        )
        grown = finance.compound_interest(10000, 0.06, 20)
        self.assertGreater(grown, 30000)
        self.assertLess(grown, 35000)

    def test_loan_payment(self):
        payment = finance.loan_payment(250000, 0.05, 30)
        self.assertAlmostEqual(payment, 1342.05, places=1)
        self.assertAlmostEqual(finance.loan_payment(1200, 0.0, 1), 100.0, places=6)
        with self.assertRaises(ValueError):
            finance.loan_payment(1000, 0.05, 0)

    def test_real_value_and_rule_of_72(self):
        self.assertAlmostEqual(finance.real_value(100, 0.10, 1), 90.909, places=2)
        self.assertAlmostEqual(finance.rule_of_72(0.09), 8.0, places=6)
        with self.assertRaises(ValueError):
            finance.rule_of_72(0)

    def test_budget_split(self):
        self.assertEqual(finance.budget_5030_20(3000), (1500.0, 900.0, 600.0))

    def test_solve_money_handles_common_questions(self):
        loan = finance.solve_money(
            "monthly payment on a 250000 mortgage at 5% over 30 years"
        )
        self.assertIsNotNone(loan)
        self.assertIn("1,342.05", loan)

        savings = finance.solve_money("invest 10k at 6% for 20 years")
        self.assertIsNotNone(savings)
        self.assertIn("33,102", savings)

        inflation = finance.solve_money(
            "what is 50000 worth in 10 years with 3% inflation"
        )
        self.assertIsNotNone(inflation)
        self.assertIn("37,204", inflation)

        doubling = finance.solve_money("how long does money double at 7%")
        self.assertIsNotNone(doubling)
        self.assertIn("10.3 years", doubling)

        budget = finance.solve_money("50/30/20 budget on 3000 a month")
        self.assertIsNotNone(budget)
        self.assertIn("1,500.00", budget)

        fund = finance.solve_money("emergency fund on 1800 a month")
        self.assertIsNotNone(fund)
        self.assertIn("10,800.00", fund)

    def test_solve_money_returns_none_when_unrecognised(self):
        self.assertIsNone(finance.solve_money("tell me a joke"))
        self.assertIsNone(finance.solve_money(""))


class FinancialAdviceTests(unittest.TestCase):
    def test_advice_picks_the_matching_playbook(self):
        self.assertIn("debt", finance.advice("how do I get out of debt").lower())
        self.assertIn("index funds", finance.advice("how should I start investing"))
        self.assertIn("employer match", finance.advice("am I saving enough for retirement"))

    def test_advice_falls_back_to_the_basics(self):
        answer = finance.advice("be my financial advisor")
        self.assertIn("Spend less than you earn", answer)

    def test_every_answer_carries_the_disclaimer(self):
        self.assertIn(finance.DISCLAIMER, finance.advice("budget help"))


class FinanceSkillRoutingTests(unittest.TestCase):
    def setUp(self):
        self.assistant = Assistant()

    def respond(self, text):
        return self.assistant.respond(text)

    def test_economics_terms_route_to_the_economics_skill(self):
        self.assertTrue(self.respond("what is inflation?").startswith("Inflation:"))
        self.assertTrue(self.respond("explain compound interest").startswith("Compound interest:"))
        self.assertTrue(self.respond("economics").startswith("Economics:"))

    def test_economics_topics_lists_entries(self):
        answer = self.respond("economics topics")
        self.assertIn("Emergency fund", answer)
        self.assertIn(str(len(finance.ENTRIES)), answer)

    def test_unknown_economics_subject_suggests_topics(self):
        answer = self.respond("economics: quantum tulip futures")
        self.assertIn("I do not have an economics entry", answer)

    def test_money_questions_route_to_money_math(self):
        answer = self.respond("monthly payment on a 250000 mortgage at 5% over 30 years")
        self.assertIn("1,342.05", answer)
        self.assertIn(finance.DISCLAIMER, answer)

    def test_advice_questions_route_to_the_advisor(self):
        answer = self.respond("financial advice on investing")
        self.assertIn("index funds", answer)
        self.assertIn(finance.DISCLAIMER, answer)

    def test_existing_skills_still_win(self):
        self.assertIn("It is", self.respond("what is the time?"))
        self.assertEqual(self.respond("calculate 21 * 2"), "21 * 2 = 42")
        self.assertTrue(self.respond("what is gravity?").startswith("Gravity:"))
        self.assertIn("speed = 15 m/s", self.respond("how fast is a car that travels 150 m in 10 s"))


if __name__ == "__main__":
    unittest.main()
