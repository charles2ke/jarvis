import sys
import unittest

from jarvis import papertrade
from jarvis.memory import Memory

KEY = papertrade.PORTFOLIO_KEY
ENDING = papertrade.SAFETY_LINE + "\n" + papertrade.CREDIT
BAD_QUANTITY = "Shares must be a whole number between 1 and 10,000."


def _order(symbol="AAPL", side="buy", quantity=1):
    return {"symbol": symbol, "side": side, "quantity": quantity}


def _portfolio(**positions):
    return {
        "cash": 1,
        "positions": {symbol: position for symbol, position in positions.items()},
    }


class OrderRulesTests(unittest.TestCase):
    # Golden values from OpenTrading test/trading.test.js.

    def test_validates_every_order_constraint(self):
        empty = papertrade.create_portfolio()
        cases = [
            (_order("UNKNOWN"), "Select a supported stock."),
            (_order(quantity=0), BAD_QUANTITY),
            (_order(quantity=10_001), BAD_QUANTITY),
            (_order(quantity=1.5), BAD_QUANTITY),
            (_order(side="hold"), "Choose buy or sell."),
            (_order(quantity=10_000), "This order exceeds your available cash."),
            (_order(side="sell"), "You cannot sell more shares than you own."),
            (_order(quantity="2"), ""),
            # Jarvis-specific: JavaScript reads true as 1 share; Jarvis refuses it.
            (_order(quantity=True), BAD_QUANTITY),
        ]
        for order, message in cases:
            with self.subTest(order=order):
                self.assertEqual(papertrade.validate_order(empty, order), message)

    def test_buys_adds_to_partially_sells_and_closes_a_position(self):
        first, error = papertrade.execute_order(papertrade.create_portfolio(), _order(quantity=2))
        self.assertEqual(error, "")
        self.assertEqual(first["positions"]["AAPL"]["quantity"], 2)
        self.assertEqual(first["cash"], 100_000 - 464.28)
        second, _ = papertrade.execute_order(first, _order(quantity=1))
        self.assertEqual(second["positions"]["AAPL"], {"quantity": 3, "averagePrice": 232.14})
        partial, _ = papertrade.execute_order(second, _order(side="sell"))
        self.assertEqual(partial["positions"]["AAPL"], {"quantity": 2, "averagePrice": 232.14})
        closed, _ = papertrade.execute_order(partial, _order(side="sell", quantity=2))
        self.assertEqual(closed["positions"], {})
        self.assertEqual(closed["cash"], 100_000)
        self.assertEqual(first["positions"]["AAPL"]["quantity"], 2)

    def test_invalid_order_returns_the_same_portfolio(self):
        portfolio = papertrade.create_portfolio()
        result, error = papertrade.execute_order(portfolio, _order(side="sell"))
        self.assertIs(result, portfolio)
        self.assertEqual(error, "You cannot sell more shares than you own.")

    def test_summarizes_empty_profitable_and_losing_positions(self):
        empty = papertrade.summarize_portfolio(papertrade.create_portfolio())
        self.assertEqual(
            (empty.cash, empty.positions, empty.portfolio_value, empty.daily_change),
            (100_000, (), 100_000, 0),
        )
        summary = papertrade.summarize_portfolio({
            "cash": 50_000,
            "positions": {
                "AAPL": {"quantity": 2, "averagePrice": 200},
                "MSFT": {"quantity": 1, "averagePrice": 450},
            },
        })
        tolerance = sys.float_info.epsilon * 256
        self.assertLess(abs(summary.positions[0].return_value - 64.28), tolerance)
        self.assertLess(abs(summary.positions[1].return_value + 31.21), tolerance)
        self.assertLess(abs(summary.portfolio_value - 50_883.07), tolerance)
        self.assertGreater(summary.daily_change, 0)


class PortfolioStateTests(unittest.TestCase):
    # Golden values from OpenTrading test/trading.test.js and test/storage.test.js.

    def test_recognizes_only_structurally_valid_portfolios(self):
        self.assertTrue(papertrade.is_portfolio(
            _portfolio(AAPL={"quantity": 1, "averagePrice": 100})
        ))
        invalid = [
            None,
            "portfolio",
            {"cash": "1", "positions": {}},
            {"cash": -1, "positions": {}},
            {"cash": 1},
            {"cash": 1, "positions": []},
            _portfolio(BAD={"quantity": 1, "averagePrice": 1}),
            _portfolio(AAPL=None),
            _portfolio(AAPL={"quantity": 1.2, "averagePrice": 1}),
            _portfolio(AAPL={"quantity": 0, "averagePrice": 1}),
            _portfolio(AAPL={"quantity": 1, "averagePrice": "1"}),
            _portfolio(AAPL={"quantity": 1, "averagePrice": 0}),
        ]
        for value in invalid:
            with self.subTest(value=value):
                self.assertFalse(papertrade.is_portfolio(value))

    def test_loads_valid_state_and_falls_back_for_invalid_state(self):
        memory = Memory(None)
        fresh = {"cash": 100_000, "positions": {}}
        self.assertEqual(papertrade.load_portfolio(memory), fresh)
        memory.set(KEY, {})
        self.assertEqual(papertrade.load_portfolio(memory), fresh)
        saved = {"cash": 500, "positions": {"AAPL": {"quantity": 1, "averagePrice": 200}}}
        papertrade.save_portfolio(memory, saved)
        self.assertEqual(papertrade.load_portfolio(memory), saved)
        with self.assertRaisesRegex(TypeError, r"^Refusing to store an invalid portfolio\.$"):
            papertrade.save_portfolio(memory, {})


class SearchTests(unittest.TestCase):
    # Golden values from OpenTrading test/trading.test.js.

    def test_searches_instruments_across_names_exchanges_and_identifiers(self):
        for query in ("", "   ", None, ",,"):
            self.assertEqual(len(papertrade.search_instruments(query)), 6)
        cases = {
            "hsbc": ["HSBA"],
            "XETRA": ["SAP"],
            "US88160R1014": ["TSLA"],
            "US-8816-0R1014": ["TSLA"],
            "594918104": ["MSFT"],
            "2046251": ["AAPL"],
            "aapl.": ["AAPL"],
            "apple nasdaq": ["AAPL"],
            "apple lse": [],
            "zzzz": [],
            "tsla, msft": ["MSFT", "TSLA"],
            "apple nasdaq, hsbc": ["AAPL", "HSBA"],
        }
        for query, symbols in cases.items():
            with self.subTest(query=query):
                found = papertrade.search_instruments(query)
                self.assertEqual([item.symbol for item in found], symbols)

    def test_searches_indices_by_name_and_code(self):
        def codes(query):
            return [index.code for index in papertrade.search_indices(query)]

        self.assertEqual(codes("nikkei, dax"), ["NKY", "DAX"])
        self.assertEqual(codes("nikkei"), ["NKY"])
        self.assertEqual([index.name for index in papertrade.search_indices("ukx")], ["FTSE 100"])
        self.assertEqual(codes("s&p"), ["SPX"])
        self.assertEqual(len(codes("")), 4)
        self.assertEqual(codes("zzzz"), [])

    def test_resolves_company_names_and_identifiers(self):
        cases = {
            "Tesla": "TSLA",
            "apple inc.": "AAPL",
            "Toyota": "7203",
            "HSBC Holdings": "HSBA",
            "us-0378331005": "AAPL",
            "apple nasdaq": "AAPL",
        }
        for query, symbol in cases.items():
            with self.subTest(query=query):
                self.assertEqual(papertrade.resolve_instrument(query).symbol, symbol)
        self.assertIsNone(papertrade.resolve_instrument("google"))
        self.assertIsNone(papertrade.resolve_instrument("nasdaq"))
        self.assertIsNone(papertrade.resolve_instrument("apple nasdaq", fuzzy=False))


class HandleTests(unittest.TestCase):
    def setUp(self):
        self.memory = Memory(None)

    def ask(self, text):
        reply = papertrade.handle(text, self.memory)
        self.assertIsNotNone(reply, text)
        self.assertTrue(reply.endswith(ENDING), reply)
        return reply

    def test_paper_orders_fill_at_demo_prices_and_persist(self):
        reply = self.ask("paper buy 10 AAPL")
        self.assertIn("Bought 10 AAPL (Apple) at the demo price of $232.14 (paper trade).", reply)
        self.assertIn("- Cost: $2,321.40\n- Cash left: $97,678.60\n", reply)
        stored = self.memory.get(KEY)
        self.assertAlmostEqual(stored["cash"], 97_678.60, places=6)
        self.assertEqual(list(stored["positions"]), ["AAPL"])
        self.assertEqual(stored["positions"]["AAPL"]["quantity"], 10)
        # OpenTrading's float maths gives 232.13999999999996 here too.
        self.assertAlmostEqual(stored["positions"]["AAPL"]["averagePrice"], 232.14, places=9)
        reply = self.ask("paper sell 5 shares of Apple")
        self.assertIn("Sold 5 AAPL (Apple) at the demo price of $232.14", reply)
        self.assertEqual(self.memory.get(KEY)["positions"]["AAPL"]["quantity"], 5)

    def test_understands_company_names_number_words_and_sell_all(self):
        self.assertIn("Bought 3 MSFT (Microsoft)", self.ask("simulate buying 3 Microsoft"))
        self.assertIn("Bought 10 TSLA (Tesla)", self.ask("paper buy ten shares of tesla"))
        self.assertIn("Sold 3 MSFT", self.ask("paper sell all my Microsoft shares"))
        self.assertEqual(list(self.memory.get(KEY)["positions"]), ["TSLA"])
        # "Bought 4 7203" would read as one number, so numeric symbols get "shares of".
        self.assertIn("Bought 4 shares of 7203 (Toyota Motor)", self.ask("papertrade buy 4 toyota"))

    def test_rejected_orders_explain_and_store_nothing(self):
        reply = self.ask("paper sell 5 shares of Tesla")
        self.assertIn("Paper order not placed: You cannot sell more shares than you own.", reply)
        reply = self.ask("paper buy 1000 AAPL")
        self.assertIn("This order exceeds your available cash.", reply)
        self.assertIn("paper buy 430 AAPL", reply)
        self.assertIn("is not one of OpenTrading's demo stocks", self.ask("paper buy 10 google"))
        self.assertIsNone(self.memory.get(KEY))

    def test_shows_and_resets_the_portfolio(self):
        self.assertIn(
            "Your paper portfolio holds $100,000.00 in cash and no positions.",
            self.ask("show my paper portfolio"),
        )
        self.ask("paper buy 2 AAPL")
        reply = self.ask("paper portfolio")
        self.assertIn("- AAPL (Apple, NASDAQ): 2 shares at an average $232.14; demo price", reply)
        self.assertIn("- Total value: $100,000.00", reply)
        self.assertIn("- Today: +$6.76 versus the previous close", reply)
        self.assertIn("Cleared 1 position.", self.ask("reset my paper portfolio"))
        self.assertEqual(self.memory.get(KEY), {"cash": 100_000, "positions": {}})

    def test_quotes_lookups_indices_and_help(self):
        quote = self.ask("paper quote AAPL")
        self.assertIn(
            "AAPL (Apple, NASDAQ, US): demo price $232.14, +1.48% on the previous close of "
            "$228.76.",
            quote,
        )
        self.assertEqual(self.ask("look up ISIN US0378331005"), quote)
        indices = self.ask("paper indices")
        self.assertIn("- S&P 500 (SPX): 6,481.4, +0.72%", indices)
        self.assertIn("- Nikkei 225 (NKY): 42,520.27, -0.46%", indices)
        self.assertEqual(self.ask("paper trading help"), papertrade.usage())

    def test_never_places_real_trades(self):
        reply = self.ask("buy 10 shares of Apple")
        self.assertIn("I can't place real trades", reply)
        self.assertIn("say: paper buy 10 AAPL", reply)
        self.assertIsNone(self.memory.get(KEY))

    def test_questions_limit_prices_and_dollar_amounts_are_explained_not_filled(self):
        self.assertIn(
            "To place that paper order, say: paper buy 10 AAPL",
            self.ask("how do I paper buy 10 AAPL?"),
        )
        self.assertIn("no limit or stop orders", self.ask("paper buy 10 AAPL at $200"))
        self.assertIn("$500.00 is 36 shares of HSBA", self.ask("paper buy $500 of hsbc"))
        self.assertIsNone(self.memory.get(KEY))

    def test_ignores_requests_that_are_not_paper_trading(self):
        for text in (
            "buy milk",
            "buy 2 apples",
            "simulate a coin flip",
            "what is the weather",
            "I bought 10 shares of apple last year",
            "history of paper money",
            "",
        ):
            with self.subTest(text=text):
                self.assertIsNone(papertrade.handle(text, self.memory))

    def test_usage_examples_work_in_order(self):
        examples = [line[2:] for line in papertrade.usage().splitlines() if line.startswith("- ")]
        self.assertGreaterEqual(len(examples), 8)
        for example in examples:
            with self.subTest(example=example):
                reply = self.ask(example)
                self.assertNotEqual(reply, papertrade.usage())
                self.assertNotIn("not placed", reply)


if __name__ == "__main__":
    unittest.main()
