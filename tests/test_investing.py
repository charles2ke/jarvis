import re
import unittest

from project_support import ProjectTestCase, fake_project, missing_projects

from jarvis import projects
from jarvis.investing import CREDIT, DISCLAIMER, solve, usage

ENDING = DISCLAIMER + "\n" + CREDIT


# Made-up answers in the shapes bridges/portfolio-watcher.mjs returns.
def _valuation(**changes):
    result = {
        "years": [{"year": 1}, {"year": 2}, {"year": 3}],
        "pvOfForecast": 120.0,
        "terminalValue": 400.0,
        "pvOfTerminalValue": 300.0,
        "enterpriseValue": 420.0,
        "equityValue": 440.0,
        "valuePerShare": 44.0,
        "currentPrice": 30.0,
        "upsidePercent": 46.67,
        "method": "perpetuity",
    }
    result.update(changes)
    return result


def _dcf(value=None, perpetuity=None, discount=0.1, terminal=0.01):
    return {
        "value": value or _valuation(),
        "perpetuity": perpetuity,
        "discountRate": discount,
        "terminalGrowth": terminal,
        "riskFreeRate": 0.02,
        "equityRiskPremium": 0.055,
    }


def _risk(**changes):
    result = {
        "count": 3,
        "volatility": 0.4,
        "valueAtRisk": 0.1,
        "expectedShortfall": 0.12,
        "maxDrawdown": 0.2,
        "mean": 0.01,
        "median": 0.02,
        "stdDev": 0.06,
        "skewness": -0.5,
        "kurtosis": 1.25,
        "tStatistic": 0.35,
        "annualisedReturnPercent": 150.0,
    }
    result.update(changes)
    return result


def _year(year, dividends, value, yield_on_cost):
    return {
        "year": year,
        "dividendIncome": dividends,
        "endingValue": value,
        "yieldOnCost": yield_on_cost,
    }


class FakeProjectTestCase(unittest.TestCase):
    def fake(self, **answers):
        faked = fake_project("Portfolio-Watcher", answers)
        calls = faked.__enter__()
        self.addCleanup(faked.__exit__, None, None, None)
        return calls

    def assertReply(self, reply, *fragments):
        self.assertIsNotNone(reply)
        for fragment in fragments:
            self.assertIn(fragment, reply)
        self.assertTrue(reply.endswith(ENDING), reply)


class RoutingTests(unittest.TestCase):
    def test_other_or_incomplete_text_needs_no_project(self):
        with missing_projects():
            for text in (
                "what is the weather",
                "buy milk",
                "my beta fish is 2 years old",
                "fibonacci sequence",
                "what is a dividend",
                "dcf",
                "rsi",
                "sharpe ratio",
                "invest 7000 at 5.5% for 15 years",
            ):
                with self.subTest(text=text):
                    self.assertIsNone(solve(text))

    def test_usage_works_without_the_project(self):
        with missing_projects():
            text = usage()
        self.assertTrue(text.startswith("I can do investment maths with Portfolio-Watcher's"))
        self.assertIn("- cost of equity for beta 1.3", text)
        self.assertTrue(text.endswith(ENDING))


class CapmTests(FakeProjectTestCase):
    def setUp(self):
        self.calls = self.fake(
            capm={"costOfEquity": 0.095, "riskFreeRate": 0.03, "equityRiskPremium": 0.0625}
        )

    def test_cost_of_equity_comes_from_the_project(self):
        reply = solve("cost of equity for beta 1.04")
        self.assertEqual(self.calls, [("capm", {"beta": 1.04})])
        self.assertTrue(reply.startswith("Cost of equity (CAPM): 9.50%\n"))
        self.assertReply(
            reply,
            "- Risk-free 3% + beta 1.04 x equity risk premium 6.25% = 9.50%",
            "are Portfolio-Watcher's own",
        )

    def test_typed_rates_are_reported_as_unused(self):
        reply = solve("capm beta 0.8 risk-free 1% erp 7%")
        self.assertEqual(self.calls, [("capm", {"beta": 0.8})])
        self.assertReply(
            reply, "The risk-free rate of 1% and equity risk premium of 7% you gave were not used"
        )


class DcfTests(FakeProjectTestCase):
    def test_typed_numbers_are_sent_to_the_project(self):
        calls = self.fake(dcf=_dcf())
        reply = solve(
            "dcf fcf 50m growth 4% discount 10% 3 years terminal 1% net cash 20m "
            "10m shares price $30"
        )
        self.assertEqual(calls, [("dcf", {
            "fcf": 50e6, "growth": 0.04, "years": 3, "discount": 0.1, "beta": None,
            "terminalGrowth": 0.01, "exitMultiple": None, "netDebt": -20e6,
            "shares": 10e6, "price": 30.0,
        })])
        self.assertTrue(reply.startswith("DCF value: $44.00 a share\n"))
        self.assertReply(
            reply,
            "- Present value of 3 years of free cash flow: $120.00",
            "- Terminal value: $400.00, worth $300.00 today",
            "- Equity value: $440.00",
            "- Implied upside against the $30.00 price: +46.67%",
            "- Most of the value comes from beyond the forecast",
            "- Terminal value: cash flow grows 1% a year forever after year 3.",
            "- Net cash of $20,000,000 is added to reach equity value.",
        )

    def test_values_typed_before_their_keywords(self):
        calls = self.fake(dcf=_dcf())
        solve(
            "dcf: 40m fcf, 6% growth, 11% discount, 1.5% terminal growth, 8m shares, "
            "10m net debt"
        )
        self.assertEqual(calls[0][1], {
            "fcf": 40e6, "growth": 0.06, "years": None, "discount": 0.11, "beta": None,
            "terminalGrowth": 0.015, "exitMultiple": None, "netDebt": 10e6,
            "shares": 8e6, "price": None,
        })

    def test_a_beta_uses_the_projects_estimate_and_defaults(self):
        calls = self.fake(dcf=_dcf(discount=0.1025, terminal=0.02))
        reply = solve("dcf fcf 1,000 growth 5% beta 1.5")
        self.assertEqual(calls[0][1]["beta"], 1.5)
        self.assertIsNone(calls[0][1]["discount"])
        self.assertReply(
            reply,
            "for 3 years (Portfolio-Watcher's default)",
            "Discount rate 10.25% from Portfolio-Watcher's CAPM estimate: 2% + 1.5 x 5.5%.",
            "grows 2% a year forever after year 3, Portfolio-Watcher's default rate.",
            "Add shares outstanding",
        )

    def test_an_exit_multiple_is_compared_with_a_perpetuity(self):
        calls = self.fake(dcf=_dcf(perpetuity=_valuation(valuePerShare=55.5)))
        reply = solve("dcf fcf 100 discount 9% exit multiple 10x terminal 2% 5 shares")
        self.assertEqual(calls[0][1]["exitMultiple"], 10.0)
        self.assertEqual(calls[0][1]["terminalGrowth"], 0.02)
        self.assertReply(
            reply,
            "10x final-year free cash flow as an exit multiple",
            "- For comparison, a 2% growing perpetuity gives 55.50 a share",
        )

    def test_no_terminal_value_is_explained(self):
        missing = dict.fromkeys(
            ("terminalValue", "pvOfTerminalValue", "enterpriseValue", "equityValue",
             "valuePerShare", "upsidePercent")
        )
        self.fake(dcf=_dcf(value=_valuation(**missing), discount=0.03, terminal=0.04))
        reply = solve("dcf fcf 100 discount 3% terminal 4%")
        self.assertTrue(reply.startswith(
            "Portfolio-Watcher has no terminal value for a 3% discount rate with 4% terminal growth"
        ))
        self.assertReply(reply, '"exit multiple 12x"')

    def test_inputs_out_of_range_are_refused_without_the_project(self):
        with missing_projects():
            for text, problem in (
                ("dcf fcf 100 discount 9% for 80 years", "the forecast must run for 1 to 50 years"),
                ("dcf fcf 100 discount 9% exit multiple 0x", "the exit multiple must be above zero"),
                ("dcf fcf 1" + "0" * 400 + " discount 9%", "one of those numbers is too large"),
            ):
                with self.subTest(text=text[:40]):
                    self.assertTrue(solve(text).startswith(f"I couldn't work that out: {problem}"))

    def test_an_unexpected_answer_is_an_error(self):
        for data in (
            None,
            _dcf(value=_valuation(years=[])),
            _dcf(value=_valuation(pvOfForecast="120")),
            _dcf(value=_valuation(enterpriseValue=None)),
            dict(_dcf(), discountRate=None),
        ):
            with self.subTest(data=str(data)[:60]):
                with fake_project("Portfolio-Watcher", {"dcf": data}):
                    with self.assertRaises(projects.ProjectError):
                        solve("dcf fcf 100 discount 9%")


class FibonacciTests(FakeProjectTestCase):
    def test_levels_come_from_the_project(self):
        levels = [
            {"label": "0%", "value": 90.0},
            {"label": "half", "value": 65.0},
            {"label": "100%", "value": 40.0},
        ]
        calls = self.fake(fibonacci=levels)
        reply = solve("fibonacci levels between 90 and 40")
        self.assertEqual(calls, [("fibonacci", {"low": 40.0, "high": 90.0})])
        self.assertTrue(reply.startswith(
            "Fibonacci retracements from 90 down to 40:\n- 0%: 90.00\n- half: 65.00\n- 100%: 40.00\n"
        ))

    def test_a_high_equal_to_the_low_is_refused(self):
        with missing_projects():
            reply = solve("fib levels between 5 and 5")
        self.assertTrue(reply.startswith("Fibonacci levels need a high and a low that differ."))


class TechnicalsTests(FakeProjectTestCase):
    def test_one_call_with_the_projects_defaults(self):
        calls = self.fake(technicals={
            "rsi": [None, None, None, None, 61.5],
            "macd": {
                "macd": [None, None, None, 0.4, 0.5],
                "signal": [None, None, None, None, 0.45],
                "histogram": [None, None, None, None, 0.05],
            },
        })
        reply = solve("rsi and macd of 3, 7, 4, 9, 6")
        self.assertEqual(calls, [("technicals", {
            "values": [3.0, 7.0, 4.0, 9.0, 6.0],
            "rsi": {"period": None},
            "macd": {"fast": None, "slow": None, "signal": None},
        })])
        self.assertTrue(reply.startswith("Technical readings for the 5 values you typed"))
        self.assertReply(
            reply,
            "- RSI: 61.50",
            "- MACD: line 0.5000, signal 0.4500, histogram 0.0500; the line is above the signal",
            "No RSI period was given, so it uses Portfolio-Watcher's default.",
            "MACD uses Portfolio-Watcher's default periods.",
        )

    def test_a_moving_average_without_a_period_uses_every_value(self):
        calls = self.fake(technicals={"ema": [None, None, None, 5.0]})
        reply = solve("ema of 3, 5, 4, 8")
        self.assertEqual(calls[0][1]["ema"], {"period": 4})
        self.assertTrue(reply.startswith("EMA(4): 5.00; the latest value 8.00 is above it\n"))
        self.assertReply(
            reply,
            "No EMA period was given, so it uses all 4 values.",
            "EMA(4) has a single reading, the plain average of all 4 values;",
        )

    def test_typed_bollinger_settings(self):
        calls = self.fake(technicals={"bollinger": {
            "upper": [None, None, 6.0, 7.5],
            "middle": [None, None, 5.0, 6.0],
            "lower": [None, None, 4.0, 4.5],
        }})
        reply = solve("bollinger(3, 1.5) of 4 6 5 7")
        self.assertEqual(calls[0][1]["bollinger"], {"period": 3, "multiple": 1.5})
        self.assertTrue(reply.startswith(
            "Bollinger(3, 1.5): upper 7.50, middle 6.00, lower 4.50; the latest value 7.00 "
            "is inside the bands\n"
        ))

    def test_too_few_values(self):
        calls = self.fake(technicals={"sma": [None, None, None]})
        reply = solve("sma 10 of 4, 8, 6")
        self.assertEqual(calls[0][1], {"values": [4.0, 8.0, 6.0], "sma": {"period": 10}})
        self.assertTrue(reply.startswith(
            "Not enough values for SMA(10): you gave 3. Add more values or choose a shorter period."
        ))

    def test_numbers_apart_from_the_series_are_left_out(self):
        calls = self.fake(technicals={"rsi": [None, None, None, None, None, 55.0]})
        reply = solve("rsi for the last 6 closes: 10 11 12 11 13 14")
        self.assertEqual(calls[0][1]["values"], [10.0, 11.0, 12.0, 11.0, 13.0, 14.0])
        self.assertReply(reply, "Left out 6, typed apart from the series.")

    def test_problems_found_before_asking_the_project(self):
        with missing_projects():
            for text, problem in (
                ("macd(8, 5, 3) of 4, 8, 6", "the MACD fast period must be shorter"),
                ("volatility of 20% over 5 years", "those numbers are in 2 separate groups"),
            ):
                with self.subTest(text=text):
                    self.assertTrue(solve(text).startswith(f"I couldn't work that out: {problem}"))

    def test_an_unexpected_series_is_an_error(self):
        for series in ([1.0, 2.0], ["1", None, None], None):
            with self.subTest(series=series):
                with fake_project("Portfolio-Watcher", {"technicals": {"sma": series}}):
                    with self.assertRaises(projects.ProjectError):
                        solve("sma 2 of 4, 8, 6")


class RiskTests(FakeProjectTestCase):
    def test_prices_go_to_the_project(self):
        calls = self.fake(risk=_risk())
        reply = solve("max drawdown of 50, 60, 45, 70")
        payload = {"values": [50.0, 60.0, 45.0, 70.0], "prices": True, "confidence": None}
        self.assertEqual(calls, [("risk", payload)])
        self.assertTrue(reply.startswith("Max drawdown: 20.00%\n"))
        self.assertReply(
            reply,
            "- Annualised return: 150.00%",
            "- Annualised volatility: 40.00%",
            "- Historical VaR: 10.00% in one period",
            "- Expected shortfall: 12.00%",
            "- Per period: mean 1.00%, median 2.00%, standard deviation 6.00%",
            "- Skewness -0.50, excess kurtosis 1.25, t-statistic 0.35",
            "Read the 4 numbers as prices",
            "Portfolio-Watcher's default confidence level",
        )

    def test_a_typed_confidence_and_monthly_returns(self):
        calls = self.fake(risk=_risk())
        reply = solve("99% var of monthly returns 1%, -2%, 0.5%")
        payload = {"values": [0.01, -0.02, 0.005], "prices": False, "confidence": 0.99}
        self.assertEqual(calls, [("risk", payload)])
        self.assertTrue(reply.startswith("Historical 99% VaR: 10.00% in one period\n"))
        self.assertNotIn("- Annualised", reply)
        self.assertReply(reply, "no annualised volatility or return for monthly figures")

    def test_what_the_project_cannot_work_out_is_refused(self):
        refusals = {
            "sharpe ratio of returns 1%, 2%, -1%": "Portfolio-Watcher has no Sharpe ratio",
            "sharpe ratio with return 10% and volatility 15%": "Portfolio-Watcher has no Sharpe",
            "annualised return of returns 1%, 2%, -1%": "Portfolio-Watcher works out an",
            "volatility of monthly returns 1%, 2%, -1%": "Portfolio-Watcher annualises",
            "max drawdown of 100, 0, 90": "Prices must all be above zero",
        }
        with missing_projects():
            for text, problem in refusals.items():
                with self.subTest(text=text):
                    self.assertTrue(solve(text).startswith(problem))

    def test_an_unexpected_answer_is_an_error(self):
        for data in (_risk(count="3"), _risk(volatility=None),
                     _risk(annualisedReturnPercent=None)):
            with self.subTest(data=data), fake_project("Portfolio-Watcher", {"risk": data}):
                with self.assertRaises(projects.ProjectError):
                    solve("volatility of 50, 60, 45, 70")


class DripTests(FakeProjectTestCase):
    def test_years_give_a_year_by_year_projection(self):
        calls = self.fake(drip={
            "reinvest": [_year(1, 30.0, 2730.0, 2.0), _year(2, 54.6, 3984.6, 2.02)],
            "payout": [_year(1, 30.0, 2700.0, 2.0), _year(2, 54.0, 3900.0, 2.0)],
        })
        reply = solve("drip 1500 at 2% yield plus 100 a month for 2 years")
        self.assertEqual(calls, [("drip", {
            "initialInvestment": 1500.0, "annualContribution": 1200.0,
            "startingYieldPercent": 2.0, "dividendGrowth": 0.0, "priceGrowth": 0.0, "years": 2,
        })])
        self.assertTrue(reply.startswith(
            "DRIP projection: 1,500.00 plus 100.00 a month grows to 3,984.60 in 2 years "
            "with dividends reinvested\n"
        ))
        self.assertReply(
            reply,
            "- Year 2: dividends 54.60, value 3,984.60, yield on cost 2.02%",
            "- Taking dividends as cash instead: value 3,900.00",
            "100.00 a month goes in as 1,200.00 at each year end.",
        )

    def test_without_years_the_projects_horizons_are_shown(self):
        calls = self.fake(drip={
            "reinvest": [{"horizon": 3, "finalValue": 1200.0, "annualIncome": 40.0},
                         {"horizon": 6, "finalValue": 1500.0, "annualIncome": 55.0}],
            "payout": [{"horizon": 3, "finalValue": 1000.0, "annualIncome": 30.0},
                       {"horizon": 6, "finalValue": 1000.0, "annualIncome": 30.0}],
        })
        reply = solve("drip 1000 at 3% yield paid out")
        self.assertIsNone(calls[0][1]["years"])
        self.assertTrue(reply.startswith(
            "DRIP projection: 1,000.00 with dividends paid out:\n"
            "- After 3 years: value 1,000.00, dividends 30.00 that year\n"
        ))
        self.assertReply(
            reply,
            "- Reinvesting them instead would give 1,500.00",
            "these are the horizons Portfolio-Watcher shows",
        )

    def test_a_horizon_out_of_range(self):
        with missing_projects():
            self.assertTrue(solve("drip 1000 at 3% yield for 0 years").startswith(
                "A DRIP projection needs at least 1 year."
            ))
            self.assertIn("at most 100 years", solve("drip 1000 at 3% yield for 300 years"))

    def test_a_missing_year_is_an_error(self):
        self.fake(drip={"reinvest": [_year(1, 30.0, 1030.0, 3.0)], "payout": []})
        with self.assertRaises(projects.ProjectError):
            solve("drip 1000 at 3% yield for 2 years")


class InvestingProjectProblemTests(unittest.TestCase):
    def test_missing_project_explains_the_setup(self):
        with missing_projects(), self.assertRaises(projects.ProjectUnavailable) as raised:
            solve("cost of equity for beta 1.3")
        self.assertIn(
            "git submodule update --init projects/Portfolio-Watcher", str(raised.exception)
        )

    def test_an_unexpected_cost_of_equity_is_an_error(self):
        with fake_project("Portfolio-Watcher", {"capm": {"costOfEquity": None}}):
            with self.assertRaises(projects.ProjectError):
                solve("cost of equity for beta 1.3")


class InvestingProjectTests(ProjectTestCase):
    """Runs the real Portfolio-Watcher project from projects/ with Node.js."""

    project = "Portfolio-Watcher"

    def answer(self, text, *fragments):
        reply = solve(text)
        self.assertIsNotNone(reply, text)
        for fragment in fragments:
            self.assertIn(fragment, reply)
        self.assertTrue(reply.endswith(ENDING), reply)
        self.assertNotRegex(reply, r"\b(?:None|nan|NaN|inf)\b")
        return reply

    def test_the_site_demo(self):
        reply = self.answer("cost of equity for beta 1.3")
        self.assertRegex(reply.splitlines()[0], r"^Cost of equity \(CAPM\): \d+\.\d\d%$")

    def test_every_usage_example(self):
        examples = [line[2:] for line in usage().splitlines() if line.startswith("- ")]
        self.assertGreaterEqual(len(examples), 5)
        for example in examples:
            with self.subTest(example=example):
                self.answer(example)

    def test_answers_that_can_be_checked_by_hand(self):
        for text, fragment in (
            ("dcf fcf 80 discount 8% terminal 0% for 1 year", "- Enterprise value: 1,000.00"),
            ("sma 3 of 5, 7, 9, 11", "SMA(3): 9.00"),
            ("fibonacci levels between 40 and 90", "- 50%: 65.00"),
            ("max drawdown of 100, 120, 90, 130", "Max drawdown: 25.00%"),
            ("drip 2000 at 5% yield for 1 year",
             "- Year 1: dividends 100.00, value 2,100.00, yield on cost 5.00%"),
        ):
            with self.subTest(text=text):
                self.answer(text, fragment)

    def test_the_projects_defaults(self):
        values = ", ".join(f"{50 + 3 * ((day * 7) % 11) - day * 0.2:.1f}" for day in range(40))
        reply = self.answer(
            f"technical indicators of {values}", "- RSI: ", "- MACD: line", "- Bollinger bands: "
        )
        self.assertNotIn("Skipped", reply)
        horizons = self.answer("drip 1000 at 3.5% yield")
        self.assertGreaterEqual(len(re.findall(r"^- After \d+ years: ", horizons, re.M)), 2)


if __name__ == "__main__":
    unittest.main()
