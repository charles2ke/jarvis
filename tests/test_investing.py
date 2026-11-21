import unittest

from jarvis import investing


def _close(test, actual, expected, places=7):
    test.assertEqual(len(actual), len(expected))
    for got, want in zip(actual, expected):
        if want is None:
            test.assertIsNone(got)
        else:
            test.assertAlmostEqual(got, want, places=places)


class TechnicalsTests(unittest.TestCase):
    # Golden values from Portfolio-Watcher src/research/technicals.test.ts.

    def test_moving_averages(self):
        _close(self, investing.sma([1, 2, 3, 4], 2), [None, 1.5, 2.5, 3.5])
        _close(self, investing.ema([1, 2, 3, 4, 5], 3), [None, None, 2, 3, 4])
        _close(self, investing.ema([1, 2], 3), [None, None])

    def test_rsi_uses_wilder_smoothing(self):
        _close(self, investing.rsi([1, 2], 2), [None, None])
        _close(self, investing.rsi([1, 2, 3, 4], 2), [None, None, 100, 100])
        _close(self, investing.rsi([4, 3, 2, 1], 2), [None, None, 0, 0])
        _close(self, investing.rsi([1, 2, 1, 2], 2), [None, None, 50, 75])
        self.assertEqual(investing.rsi(list(range(1, 21)))[19], 100)

    def test_macd_line_signal_and_histogram(self):
        result = investing.macd([1, 2, 3, 4], 2, 3, 2)
        _close(self, result.macd, [None, None, 0.5, 0.5])
        _close(self, result.signal, [None, None, None, 0.5])
        _close(self, result.histogram, [None, None, None, 0])
        self.assertEqual(investing.macd([1]).macd, (None,))

    def test_bollinger_bands(self):
        bands = investing.bollinger([2, 4, 6], 2, 2)
        _close(self, bands.upper, [None, 5, 7])
        _close(self, bands.middle, [None, 3, 5])
        _close(self, bands.lower, [None, 1, 3])

    def test_fibonacci_levels(self):
        levels = [value for _, value in investing.fibonacci_levels(0, 100)]
        self.assertEqual(levels, [100, 76.4, 61.8, 50, 38.2, 21.4, 0])


class StatisticsAndRiskTests(unittest.TestCase):
    def test_descriptive_statistics(self):
        # Golden values from Portfolio-Watcher src/research/quant.test.ts.
        self.assertEqual(investing.mean([1, 2, 3]), 2)
        self.assertEqual(investing.mean([]), 0)
        self.assertEqual(investing.median([3, 1, 2]), 2)
        self.assertEqual(investing.median([1, 2, 3, 4]), 2.5)
        self.assertEqual(investing.median([]), 0)
        self.assertEqual(investing.std_dev([1, 2, 3]), 1)
        self.assertEqual(investing.std_dev([5]), 0)
        self.assertAlmostEqual(investing.skewness([1, 2, 3, 4, 5]), 0)
        self.assertEqual(investing.skewness([1, 2]), 0)
        self.assertEqual(investing.skewness([2, 2, 2]), 0)
        self.assertAlmostEqual(investing.kurtosis([1, 2, 3, 4, 5]), -1.3)
        self.assertEqual(investing.kurtosis([1, 2, 3]), 0)
        self.assertEqual(investing.kurtosis([2, 2, 2, 2]), 0)
        self.assertAlmostEqual(investing.t_statistic([1, 2, 3]), 3.4641016, places=6)
        self.assertIsNone(investing.t_statistic([1, 2]))
        self.assertIsNone(investing.t_statistic([2, 2, 2]))

    def test_var_shortfall_drawdown_and_volatility(self):
        # Golden values from Portfolio-Watcher src/research/risk.test.ts.
        losses = [-0.05, -0.02, 0, 0.01, 0.03]
        self.assertAlmostEqual(investing.historical_var(losses, 0.95), 0.05)
        self.assertAlmostEqual(investing.expected_shortfall(losses, 0.95), 0.05)
        self.assertEqual(investing.historical_var([], 0.95), 0)
        self.assertEqual(investing.historical_var([0.01, 0.02, 0.03, 0.04], 0.95), 0)
        self.assertAlmostEqual(investing.max_drawdown([0.1, -0.5, 0.2]), 0.5)
        self.assertEqual(investing.max_drawdown([]), 0)
        self.assertGreater(investing.annualised_volatility([0.01, -0.01, 0.02, -0.02]), 0)

    def test_sharpe_ratio_subtracts_the_risk_free_rate(self):
        # Monthly 1%, 2%, -1%: 8% a year and 0.0153 * sqrt(12) = 5.29% volatility,
        # so (0.08 - 0.042) / 0.052915 = 0.7181.
        self.assertAlmostEqual(
            investing.sharpe_ratio([0.01, 0.02, -0.01], 0.042, 12), 0.7181, places=4
        )
        self.assertIsNone(investing.sharpe_ratio([0.01, 0.01, 0.01]))


class ValuationTests(unittest.TestCase):
    # Golden values from Portfolio-Watcher src/research/dcf.test.ts, whose
    # fixture discounts 120 of free cash flow growing 10% at 10%.

    def test_terminal_value_perpetuity(self):
        self.assertAlmostEqual(investing.terminal_value_perpetuity(100, 0.1, 0.02), 1275)
        self.assertAlmostEqual(
            investing.terminal_value_perpetuity(193.26, 0.10, 0.02), 2464.065, places=3
        )
        self.assertIsNone(investing.terminal_value_perpetuity(100, 0.02, 0.02))
        self.assertIsNone(investing.terminal_value_perpetuity(100, 0.01, 0.02))

    def test_perpetuity_valuation(self):
        result = investing.dcf_value(
            120, 0.10, 0.10, terminal_growth=0.02, shares=100, net_debt=100, current_price=50
        )
        self.assertEqual(result.method, "perpetuity")
        self.assertAlmostEqual(result.pv_of_forecast, 600)
        self.assertAlmostEqual(result.pv_of_terminal_value, 1529.99, delta=0.05)
        self.assertAlmostEqual(result.enterprise_value, 2129.99, delta=0.05)
        self.assertAlmostEqual(result.equity_value, 2029.99, delta=0.05)
        self.assertAlmostEqual(result.value_per_share, 20.3, places=2)
        self.assertAlmostEqual(result.upside_percent, -59.4, places=1)

    def test_exit_multiple_valuation(self):
        result = investing.dcf_value(
            120, 0.10, 0.10, shares=100, net_debt=100, current_price=50,
            exit_multiple=4026.3 / (120 * 1.1 ** 5),
        )
        self.assertEqual(result.method, "exit multiple")
        self.assertAlmostEqual(result.terminal_value, 4026.3, places=1)
        self.assertAlmostEqual(result.value_per_share, 30, places=1)
        self.assertAlmostEqual(result.upside_percent, -40, places=1)

    def test_discount_rate_must_exceed_terminal_growth(self):
        with self.assertRaises(ValueError):
            investing.dcf_value(100, 0.05, 0.02, terminal_growth=0.025)


class DripTests(unittest.TestCase):
    # Golden values from Portfolio-Watcher src/research/dividends.test.ts
    # (rates here are fractions: PW's 4% yield and 4 yield-on-cost are 0.04).

    def test_first_year_with_reinvestment(self):
        rows = investing.simulate_drip(10000, 0.04, 0.05, 0.06, 2, annual_contribution=1000)
        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(
            (first.year, first.starting_value, first.contributions, first.reinvested),
            (1, 10000, 1000, 400),
        )
        self.assertAlmostEqual(first.dividend_income, 400)
        self.assertAlmostEqual(first.ending_value, 12000)
        self.assertAlmostEqual(first.yield_on_cost, 0.04)
        self.assertAlmostEqual(rows[1].starting_value, 12000)

    def test_without_reinvestment(self):
        rows = investing.simulate_drip(
            10000, 0.04, 0.05, 0.06, 1, annual_contribution=1000, reinvest=False
        )
        self.assertEqual(rows[0].reinvested, 0)
        self.assertAlmostEqual(rows[0].ending_value, 11600)

    def test_zero_investment_has_zero_yield_on_cost(self):
        rows = investing.simulate_drip(0, 0, 0, 0, 1)
        self.assertEqual((rows[0].ending_value, rows[0].yield_on_cost), (0, 0))


class SolveTests(unittest.TestCase):
    def assertReply(self, text, *fragments):
        reply = investing.solve(text)
        self.assertIsNotNone(reply, text)
        for fragment in fragments:
            self.assertIn(fragment, reply)
        self.assertTrue(reply.endswith(investing.DISCLAIMER + "\n" + investing.CREDIT), reply)
        return reply

    def test_dcf_requests(self):
        self.assertReply(
            "dcf with fcf 100m growth 8% discount 9% terminal 2.5% 50m shares net debt 200m",
            "DCF value: 35.85 a share",
            "Enterprise value: 1,992,308,014",
            "Equity value: 1,792,308,014",
            "The terminal value is 75.6% of enterprise value",
            "Assumptions:",
        )
        self.assertReply(
            "dcf: 100m fcf, 8% growth, 9% discount, 2.5% terminal growth, 50m shares, "
            "200m net debt",
            "DCF value: 35.85 a share",
        )
        self.assertReply(
            "intrinsic value with free cash flow 5bn, growth 10% for 5 years, wacc 8%, "
            "terminal growth 3%",
            "DCF equity value: 139,320,524,880",
            "Add shares outstanding",
        )

    def test_dcf_explains_a_discount_rate_below_terminal_growth(self):
        self.assertReply(
            "dcf with fcf 100 growth 5% discount 2% terminal 2.5%",
            "the discount rate (2%) must be above terminal growth (2.5%)",
        )

    def test_cost_of_equity(self):
        self.assertReply("cost of equity for beta 1.3", "Cost of equity (CAPM): 10.70%")
        self.assertReply(
            "capm beta 0.8 risk-free 3% market return 9%", "Cost of equity (CAPM): 7.80%"
        )

    def test_technicals(self):
        self.assertReply("sma 5 of 10, 11, 12, 13, 14, 15", "SMA(5): 13.00", "above it")
        self.assertReply("fibonacci levels between 100 and 150", "38.2%: 130.90", "61.8%: 119.10")
        reply = self.assertReply("rsi of 44 44.3 44.1 43.6")
        self.assertTrue(reply.startswith("RSI(14) needs at least 15 values; you gave 4."))

    def test_risk_reports_state_how_numbers_were_read(self):
        self.assertReply(
            "max drawdown of 100, 120, 90, 130",
            "Max drawdown: 25.00% (from 120 down to 90)",
            "as prices",
        )
        self.assertReply(
            "sharpe ratio of monthly returns 1%, 2%, -1%",
            "Sharpe ratio: 0.72",
            "Annualised return: 8.00%",
            "12 periods a year",
        )
        self.assertReply("volatility of returns 0.01, -0.02, 0.005", "decimal returns")
        self.assertReply("kurtosis of 1 2 3 4 5", "Excess kurtosis: -1.30")

    def test_sharpe_from_a_typed_return_and_volatility(self):
        self.assertReply(
            "what's the sharpe ratio of a fund with 8% return and 12% volatility",
            "Sharpe ratio: 0.32 (risk-free 4.2%)",
            "(8% - 4.2%) / 12% = 0.32",
        )
        self.assertReply(
            "sharpe ratio with risk free 3% and return 10% and vol 15%",
            "(10% - 3%) / 15% = 0.47",
        )
        self.assertReply("sharpe ratio of excess return 6% and volatility 12%", "6% / 12% = 0.50")

    def test_numbers_apart_from_the_series_are_not_used_as_data(self):
        reply = self.assertReply("volatility of 20% over 5 years", "separate groups (20% | 5)")
        self.assertNotIn("Annualised volatility", reply)
        closes = [44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89,
                  46.03, 45.61, 46.28, 46.28]
        self.assertReply(
            "rsi for the last 15 closes: " + " ".join(str(value) for value in closes),
            f"RSI(14): {investing.rsi(closes, 14)[-1]:.2f}",
            "Left out 15, typed apart from the series.",
        )

    def test_drip_requests(self):
        # Year one matches Portfolio-Watcher src/research/dividends.test.ts.
        self.assertReply(
            "drip 10000 at 4% yield 5% dividend growth 6% price growth adding 1000 a year "
            "for 2 years",
            "Year 1: dividends 400.00, value 12,000.00, yield on cost 4.00%",
            "Total dividends: 904.00; contributions 2,000.00",
        )
        self.assertReply(
            "drip 10000 at 4% yield 5% dividend growth 6% price growth adding 1000 a year "
            "for 1 year without reinvesting",
            "value 11,600.00",
            "with dividends paid out",
        )
        self.assertReply(
            "drip 10000 at 3% yield 5% dividend growth for 10 years",
            "DRIP projection: 10,000.00 grows to",
            "in 10 years with dividends reinvested",
            "Year 10:",
        )

    def test_usage_examples_all_work(self):
        examples = [
            line[2:] for line in investing.usage().splitlines() if line.startswith("- ")
        ]
        self.assertGreaterEqual(len(examples), 5)
        for example in examples:
            self.assertReply(example)

    def test_unrelated_or_incomplete_text_returns_none(self):
        for text in (
            "what is the weather",
            "buy milk",
            "fibonacci sequence",
            "what is a dividend",
            "rsi",
            "sharpe ratio",
            "invest 10000 at 6% for 20 years",
        ):
            self.assertIsNone(investing.solve(text), text)


if __name__ == "__main__":
    unittest.main()
