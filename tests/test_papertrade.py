import re
import unittest

from project_support import ProjectTestCase, fake_project, missing_projects

from jarvis import papertrade, projects
from jarvis.memory import Memory

KEY = papertrade.PORTFOLIO_KEY
ENDING = [papertrade.SAFETY_LINE, papertrade.CREDIT]
NOTE = papertrade.PRICE_NOTE
REFUSAL = papertrade._REFUSAL
FRESH = papertrade._FRESH_NOTE

# Made-up stocks and an index in the shape bridges/opentrading.mjs returns.
ACME = {
    "symbol": "ACME", "ticker": "ACME", "isin": "ZZ0000000017", "cusip": "000000017",
    "sedol": "0000017", "name": "Acme Rockets", "exchange": "MOON", "country": "ZZ",
    "price": 20, "previousClose": 19.5,
}
GLOBEX = {
    "symbol": "GLBX", "ticker": "GLBX", "isin": "ZZ0000000025", "cusip": "", "sedol": "",
    "name": "Globex Holdings", "exchange": "MOON", "country": "ZZ",
    "price": 1.1, "previousClose": 1.25,
}
MOON = {"name": "Moon 50", "code": "MN50", "flag": "", "value": 1234.5, "change": -0.25}
MARKET = {"startingCash": 1000, "instruments": [ACME, GLOBEX], "indices": [MOON]}
SEARCHES = {
    "ZZ0000000017": [ACME],
    "rockets": [ACME],
    "moon": [ACME, GLOBEX],
}


def _search(payload):
    query = payload["query"]
    return {"instruments": SEARCHES.get(query, []), "indices": [MOON] if query == "moon" else []}


def _holding(item, quantity, average, value, gain):
    return dict(item, quantity=quantity, averagePrice=average, value=value, returnValue=gain)


def _summary(cash, *positions, total=None, today=0):
    return {
        "cash": cash,
        "positions": list(positions),
        "portfolioValue": cash if total is None else total,
        "dailyChange": today,
    }


def _filled(portfolio, summary, quantity, *, held=0, cash_before=1000, discarded=False):
    return {
        "discarded": discarded, "error": "", "quantity": quantity, "held": held,
        "cashBefore": cash_before, "most": None, "portfolio": portfolio, "summary": summary,
    }


def _rejected(error, quantity, most, *, held=0, cash_before=1000):
    return {
        "discarded": False, "error": error, "quantity": quantity, "held": held,
        "cashBefore": cash_before, "most": most, "portfolio": None,
        "summary": _summary(cash_before),
    }


def _order(symbol, side, quantity, portfolio=None):
    return ("order", {"portfolio": portfolio, "order": {"symbol": symbol, "side": side, "quantity": quantity}})


def _clear_caches(case):
    for cached in (papertrade.market, papertrade._search):
        cached.cache_clear()
        case.addCleanup(cached.cache_clear)


class FakeMarketTestCase(unittest.TestCase):
    def setUp(self):
        _clear_caches(self)
        self.memory = Memory(None)
        self.answers = {"market": MARKET, "search": _search}
        faked = fake_project("OpenTrading", self.answers)
        self.calls = faked.__enter__()
        self.addCleanup(faked.__exit__, None, None, None)

    def lines(self, text):
        reply = papertrade.handle(text, self.memory)
        self.assertIsNotNone(reply, text)
        return reply.splitlines()


class PaperOrderTests(FakeMarketTestCase):
    def test_a_filled_order_is_explained_and_saved(self):
        saved = {"cash": 960, "positions": {"ACME": {"quantity": 2, "averagePrice": 20}}}
        self.answers["order"] = _filled(saved, _summary(960, _holding(ACME, 2, 20, 40, 0)), 2)
        self.assertEqual(self.lines("paper buy 2 ACME"), [
            "Paper order filled: bought 2 shares of ACME (Acme Rockets) at the demo price of $20.00.",
            "- Cost: $40.00",
            "- Cash left: $960.00",
            "- You now hold 2 shares of ACME at an average $20.00",
            NOTE, *ENDING,
        ])
        self.assertEqual(self.memory.get(KEY), saved)
        self.assertEqual(self.calls, [("market", None), _order("ACME", "buy", 2)])

    def test_selling_everything_sends_the_saved_portfolio(self):
        before = {"cash": 960, "positions": {"ACME": {"quantity": 2, "averagePrice": 20}}}
        after = {"cash": 1001, "positions": {}}
        self.memory.set(KEY, before)
        self.answers["order"] = _filled(after, _summary(1001), 2, held=2, cash_before=960)
        self.assertEqual(self.lines("simulate selling all my Acme shares"), [
            "Paper order filled: sold 2 shares of ACME (Acme Rockets) at the demo price of $20.00.",
            "- Proceeds: $41.00",
            "- Cash now: $1,001.00",
            "- You no longer hold any ACME",
            NOTE, *ENDING,
        ])
        self.assertEqual(self.calls[-1], _order("ACME", "sell", "all", before))
        self.assertEqual(self.memory.get(KEY), after)

    def test_a_rejected_buy_quotes_the_project_and_saves_nothing(self):
        self.answers["order"] = _rejected("Made-up refusal.", 90, 48, cash_before=960)
        self.assertEqual(self.lines("paper buy 90 shares of Acme Rockets"), [
            "Paper order not placed: Made-up refusal.",
            "- ACME's demo price is $20.00 a share, and you have $960.00 in paper cash",
            "- You can buy up to 48 shares right now: paper buy 48 ACME",
            *ENDING,
        ])
        self.assertIsNone(self.memory.get(KEY))

    def test_a_rejected_sale_says_what_is_held(self):
        cases = (
            (2, 2, ["- You hold 2 shares of ACME",
                    "- You can sell up to 2 shares right now: paper sell 2 ACME"]),
            (0, 0, ["- You hold no ACME; buy some first, e.g. paper buy 10 ACME"]),
        )
        for held, most, hints in cases:
            with self.subTest(held=held):
                self.answers["order"] = _rejected("Not that many.", 5, most, held=held)
                self.assertEqual(self.lines("paper sell 5 ACME"),
                                 ["Paper order not placed: Not that many.", *hints, *ENDING])

    def test_no_hints_when_the_amount_is_not_the_problem(self):
        for text, quantity in (("paper buy 2.5 ACME", 2.5), ("paper buy 0 ACME", 0)):
            with self.subTest(text=text):
                self.answers["order"] = _rejected("Whole shares only.", quantity, 48)
                self.assertEqual(self.lines(text), ["Paper order not placed: Whole shares only.", *ENDING])
                self.assertEqual(self.calls[-1], _order("ACME", "buy", quantity))

    def test_selling_everything_when_nothing_is_held(self):
        self.answers["order"] = _rejected("Made-up error.", 0, 0)
        self.assertEqual(self.lines("paper sell all my ACME"), [
            "Paper order not placed: you hold no ACME to sell.",
            "- Buy some first, e.g. paper buy 10 ACME",
            *ENDING,
        ])

    def test_a_saved_portfolio_the_project_refuses_is_replaced(self):
        for saved, sent, discarded in (
            ({"cash": "lots"}, {"cash": "lots"}, True),
            ({"cash": float("nan"), "positions": {}}, None, False),
        ):
            with self.subTest(saved=saved):
                self.memory.set(KEY, saved)
                fresh = {"cash": 980, "positions": {"ACME": {"quantity": 1, "averagePrice": 20}}}
                self.answers["order"] = _filled(
                    fresh, _summary(980, _holding(ACME, 1, 20, 20, 0)), 1, discarded=discarded
                )
                self.assertEqual(self.lines("paper buy 1 ACME")[-3:], [FRESH, *ENDING])
                self.assertEqual(self.calls[-1], _order("ACME", "buy", 1, sent))
                self.assertEqual(self.memory.get(KEY), fresh)

    def test_money_amounts_become_whole_shares(self):
        cases = (
            ("paper buy $50 of Acme",
             "OpenTrading orders are for a number of shares, not an amount of money: $50.00 is "
             "2 shares of ACME at the demo price of $20.00, rounded down.", "paper buy 2 ACME"),
            ("paper buy $3.30 worth of GLBX",
             "OpenTrading orders are for a number of shares, not an amount of money: $3.30 is "
             "3 shares of GLBX at the demo price of $1.10, rounded down.", "paper buy 3 GLBX"),
            ("paper sell $5 of ACME",
             "$5.00 is less than one share of ACME at the demo price of $20.00, and OpenTrading "
             "orders are for a number of shares.", "paper sell 1 ACME"),
        )
        for text, headline, command in cases:
            with self.subTest(text=text):
                self.assertEqual(self.lines(text), [headline, f"- Say: {command}", NOTE, *ENDING])
        self.assertNotIn("order", [action for action, _ in self.calls])

    def test_orders_that_are_only_explained(self):
        cases = (
            ("paper buy 2 ACME at $15", [
                "OpenTrading has no limit or stop orders: paper orders fill straight away at the "
                "demo price (ACME: $20.00).",
                "- To buy at that price, say: paper buy 2 ACME",
                NOTE,
            ]),
            ("how do I paper buy 3 ACME?", [
                "To place that paper order, say: paper buy 3 ACME",
                "- Paper orders fill straight away at the demo price; nothing real is bought or sold.",
            ]),
            ("paper buy ACME", ["How many shares of ACME? For example: paper buy 10 ACME."]),
            ("paper buy 2 ACME and 3 GLBX",
             ["One paper order at a time, please: for example, paper buy 10 AAPL."]),
            ("paper buy 3 Initech", [
                '"Initech" is not one of OpenTrading\'s demo stocks.',
                "OpenTrading's demo stocks are ACME (Acme Rockets), GLBX (Globex Holdings).",
                "- For example: paper buy 3 AAPL",
            ]),
        )
        for text, lines in cases:
            with self.subTest(text=text):
                self.assertEqual(self.lines(text), [*lines, *ENDING])
        self.assertNotIn("order", [action for action, _ in self.calls])
        self.assertIsNone(self.memory.get(KEY))

    def test_modal_order_questions_do_not_place_orders(self):
        saved = {"cash": 800, "positions": {"ACME": {"quantity": 10, "averagePrice": 20}}}
        self.memory.set(KEY, saved)
        for text in ("Can I paper buy 10 ACME?", "Could we paper sell 2 ACME?"):
            with self.subTest(text=text):
                reply = self.lines(text)
                self.assertIn("To place that paper order, say:", reply[0])
        self.assertEqual(self.memory.get(KEY), saved)
        self.assertEqual([action for action, _ in self.calls], ["market"])

    def test_polite_can_you_order_still_executes(self):
        self.answers["order"] = _filled(
            {"cash": 960, "positions": {"ACME": {"quantity": 2, "averagePrice": 20}}},
            _summary(960, _holding(ACME, 2, 20, 40, 0)),
            2,
        )
        self.lines("Can you paper buy 2 ACME?")
        self.assertEqual(self.calls[-1], _order("ACME", "buy", 2))

    def test_a_huge_number_of_shares_does_not_break_anything(self):
        self.assertEqual(self.lines("paper buy " + "9" * 400 + " ACME")[0],
                         "How many shares of ACME? For example: paper buy 10 ACME.")
        self.assertEqual(self.lines("paper buy $" + "9" * 400 + " of ACME"), papertrade.usage().splitlines())


class PortfolioTests(FakeMarketTestCase):
    def test_the_portfolio_shows_the_projects_valuation(self):
        summary = _summary(900, _holding(ACME, 3, 18, 61.5, 4.25), total=961.5, today=-1.5)
        self.answers["portfolio"] = {"discarded": False, "summary": summary}
        self.assertEqual(self.lines("show my paper portfolio"), [
            "Your paper portfolio (1 position):",
            "- ACME (Acme Rockets, MOON): 3 shares at an average $18.00; demo price $20.00, "
            "value $61.50, unrealised P/L +$4.25",
            "- Cash: $900.00",
            "- Total value: $961.50",
            "- Today: -$1.50 versus the previous close",
            NOTE, *ENDING,
        ])
        self.assertEqual(self.calls, [("portfolio", {"portfolio": None})])

    def test_an_empty_portfolio(self):
        self.answers["portfolio"] = {"discarded": True, "summary": _summary(1000)}
        self.assertEqual(self.lines("how much cash is in my paper account?"), [
            "Your paper portfolio holds $1,000.00 in cash and no positions.",
            "- Try: paper buy 10 AAPL",
            FRESH, *ENDING,
        ])

    def test_reset(self):
        self.memory.set(KEY, {"cash": 5, "positions": {"ACME": {"quantity": 1, "averagePrice": 20}}})
        fresh = {"cash": 1000, "positions": {}}
        self.answers["reset"] = {"cleared": 2, "portfolio": fresh, "summary": _summary(1000)}
        self.assertEqual(self.lines("reset my paper portfolio"), [
            "Your paper portfolio is reset to $1,000.00 in cash and no positions. Cleared 2 positions.",
            *ENDING,
        ])
        self.assertEqual(self.memory.get(KEY), fresh)

    def test_reset_questions_and_mixed_requests_change_nothing(self):
        saved = {"cash": 800, "positions": {"ACME": {"quantity": 10, "averagePrice": 20}}}
        self.memory.set(KEY, saved)
        cases = (
            ("how do I reset my paper portfolio?",
             "To start again with $1,000.00 of paper cash and no positions, say: reset my paper portfolio"),
            ("Can I reset my paper portfolio?",
             "To start again with $1,000.00 of paper cash and no positions, say: reset my paper portfolio"),
            ("Would we reset our paper portfolio?",
             "To start again with $1,000.00 of paper cash and no positions, say: reset my paper portfolio"),
            ("reset my paper portfolio and buy 2 ACME",
             'One thing at a time: say "reset my paper portfolio" to start again with $1,000.00, '
             "or give the order on its own, e.g. paper buy 10 AAPL."),
        )
        for text, line in cases:
            with self.subTest(text=text):
                self.assertEqual(self.lines(text), [line, *ENDING])
        self.assertEqual([action for action, _ in self.calls], ["market"])
        self.assertEqual(self.memory.get(KEY), saved)


class QuoteTests(FakeMarketTestCase):
    def test_quotes_show_the_demo_prices_and_codes(self):
        self.assertEqual(self.lines("paper quote ACME"), [
            "ACME (Acme Rockets, MOON, ZZ): demo price $20.00, previous close $19.50.",
            "- ISIN ZZ0000000017, CUSIP 000000017, SEDOL 0000017",
            NOTE, *ENDING,
        ])
        self.assertEqual(self.lines("demo price of globex")[:2], [
            "GLBX (Globex Holdings, MOON, ZZ): demo price $1.10, previous close $1.25.",
            "- ISIN ZZ0000000025",
        ])
        self.assertEqual(self.calls, [("market", None)])

    def test_lookups_use_the_projects_search(self):
        self.assertEqual(self.lines("look up ISIN ZZ0000000017")[0],
                         "ACME (Acme Rockets, MOON, ZZ): demo price $20.00, previous close $19.50.")
        self.assertEqual(self.lines("paper search moon"), [
            '3 demo matches for "moon":',
            "- ACME Acme Rockets (MOON, ZZ): $20.00, previous close $19.50",
            "- GLBX Globex Holdings (MOON, ZZ): $1.10, previous close $1.25",
            "- Moon 50 (MN50): 1,234.50 (-0.25%)",
            NOTE, papertrade._INDEX_NOTE, *ENDING,
        ])
        self.assertEqual(self.lines("paper search initech")[0],
                         'No OpenTrading demo stock or index matches "initech".')
        self.assertEqual([payload for action, payload in self.calls if action == "search"],
                         [{"query": "ZZ0000000017"}, {"query": "moon"}, {"query": "initech"}])

    def test_demo_stocks_and_indices(self):
        self.assertEqual(self.lines("demo stocks"), [
            "OpenTrading's demo stocks:",
            "- ACME Acme Rockets (MOON, ZZ): $20.00, previous close $19.50",
            "- GLBX Globex Holdings (MOON, ZZ): $1.10, previous close $1.25",
            NOTE, *ENDING,
        ])
        self.assertEqual(self.lines("paper indices"), [
            "Demo market indices from OpenTrading:",
            "- Moon 50 (MN50): 1,234.50 (-0.25%)",
            papertrade._INDEX_NOTE, *ENDING,
        ])
        self.assertEqual(self.lines("paper index sun"),
                         ['No demo index matches "sun". The demo indices are Moon 50 (MN50).', *ENDING])

    def test_the_market_is_read_once_and_gives_the_symbols(self):
        self.lines("paper quote ACME")
        self.lines("paper quote GLBX")
        self.assertEqual(papertrade.symbols(), ("ACME (Acme Rockets)", "GLBX (Globex Holdings)"))
        self.assertEqual(self.calls, [("market", None)])


class RealTradeTests(FakeMarketTestCase):
    def test_real_trades_are_refused_with_the_paper_command(self):
        cases = (
            ("buy 3 shares of Acme", ["- To practise with demo money instead, say: paper buy 3 ACME"]),
            ("sell all my ACME stock", ["- To practise with demo money instead, say: paper sell all my ACME"]),
            ("buy $50 of Acme stock", ["- To practise with demo money instead, say: paper buy 2 ACME"]),
            ("buy 5 shares of Initech", [
                "- To practise with demo money instead, use one of OpenTrading's demo stocks, "
                "e.g. paper buy 5 AAPL",
                "- OpenTrading's demo stocks are ACME (Acme Rockets), GLBX (Globex Holdings).",
            ]),
        )
        for text, lines in cases:
            with self.subTest(text=text):
                self.assertEqual(self.lines(text), [REFUSAL, *lines, *ENDING])
        self.assertNotIn("order", [action for action, _ in self.calls])
        self.assertIsNone(self.memory.get(KEY))


class ProjectProblemTests(unittest.TestCase):
    def setUp(self):
        _clear_caches(self)

    def test_other_messages_are_left_alone_without_the_project(self):
        texts = ("", "buy milk", "sell my car", "simulate a coin flip", "what is the weather",
                 "I bought 10 shares of apple last year", "history of paper money")
        with missing_projects():
            for text in texts:
                with self.subTest(text=text):
                    self.assertIsNone(papertrade.handle(text, Memory(None)))

    def test_help_works_without_the_project(self):
        with missing_projects():
            self.assertEqual(papertrade.handle("paper trading help", Memory(None)), papertrade.usage())

    def test_missing_project_explains_the_setup(self):
        with missing_projects(), self.assertRaises(projects.ProjectUnavailable) as raised:
            papertrade.handle("paper buy 10 ACME", Memory(None))
        self.assertIn("git submodule update --init projects/OpenTrading", str(raised.exception))
        self.assertIn(papertrade.SITE_URL, str(raised.exception))

    def test_real_trades_are_refused_even_without_the_project(self):
        with missing_projects():
            lines = papertrade.handle("buy 10 shares of ACME", Memory(None)).splitlines()
        self.assertEqual(lines[0], REFUSAL)
        self.assertIn("git submodule update --init projects/OpenTrading", lines[1])
        self.assertEqual(lines[-2:], ENDING)

    def test_unexpected_answers_are_errors(self):
        broken_markets = (
            None,
            dict(MARKET, instruments=[]),
            dict(MARKET, instruments=[dict(ACME, price="20")]),
            dict(MARKET, instruments=[dict(ACME, price=0)]),
            dict(MARKET, instruments=[dict(ACME, name="")]),
            dict(MARKET, startingCash=True),
            dict(MARKET, indices=[dict(MOON, change=None)]),
        )
        for answer in broken_markets:
            papertrade.market.cache_clear()
            with self.subTest(market=str(answer)[:60]), fake_project("OpenTrading", {"market": answer}):
                with self.assertRaises(projects.ProjectError):
                    papertrade.handle("paper quote ACME", Memory(None))
        broken = (
            ("paper buy 2 ACME", "order", {"error": None}),
            ("paper buy 2 ACME", "order", _rejected("No.", 2, -1)),
            ("paper buy 2 ACME", "order", _filled(None, _summary(1), 2)),
            ("show my paper portfolio", "portfolio", {"summary": {"cash": 1, "positions": {}}}),
            ("reset my paper portfolio", "reset", {"cleared": "2", "portfolio": {}, "summary": _summary(1)}),
        )
        for text, action, answer in broken:
            papertrade.market.cache_clear()
            memory = Memory(None)
            with self.subTest(answer=str(answer)[:60]):
                with fake_project("OpenTrading", {"market": MARKET, action: answer}):
                    with self.assertRaises(projects.ProjectError):
                        papertrade.handle(text, memory)
                self.assertIsNone(memory.get(KEY))


class OpenTradingProjectTests(ProjectTestCase):
    """Runs the real OpenTrading code from projects/OpenTrading with Node.js."""

    project = "OpenTrading"

    def setUp(self):
        _clear_caches(self)
        self.memory = Memory(None)

    def handle(self, text):
        reply = papertrade.handle(text, self.memory)
        self.assertIsNotNone(reply, text)
        self.assertEqual(reply.splitlines()[-2:], ENDING)
        return reply

    def test_the_symbols_come_from_the_project(self):
        symbols = papertrade.symbols()
        self.assertGreater(len(symbols), 1)
        for symbol in symbols:
            self.assertRegex(symbol, r"^\S+ \(.+\)$")

    def test_the_usage_examples_work_in_order(self):
        examples = [line[2:] for line in papertrade.usage().splitlines() if line.startswith("- ")]
        for example in examples:
            with self.subTest(example=example):
                self.assertNotEqual(self.handle(example), papertrade.usage())
        self.assertEqual(self.memory.get(KEY), {"cash": papertrade.market().starting_cash, "positions": {}})

    def test_buying_and_selling_back(self):
        item = papertrade.market().instruments[0]
        bought = self.handle(f"paper buy 3 {item.symbol}")
        self.assertTrue(bought.startswith(f"Paper order filled: bought 3 shares of {item.symbol} "))
        self.assertEqual(self.memory.get(KEY)["positions"][item.symbol]["quantity"], 3)
        self.assertIn("(1 position)", self.handle("show my paper portfolio"))
        sold = self.handle(f"paper sell all my {item.symbol}")
        self.assertIn(f"- You no longer hold any {item.symbol}", sold)
        saved = self.memory.get(KEY)
        self.assertEqual(saved["positions"], {})
        self.assertAlmostEqual(saved["cash"], papertrade.market().starting_cash, places=6)

    def test_the_suggested_order_after_a_rejection_fills(self):
        item = papertrade.market().instruments[0]
        rejected = self.handle(f"paper buy 999999999 {item.symbol}")
        self.assertRegex(rejected, r"^Paper order not placed: \S")
        self.assertIsNone(self.memory.get(KEY))
        suggestion = re.search(rf"right now: (paper buy \d+ {re.escape(item.symbol)})$", rejected, re.M)
        self.assertIsNotNone(suggestion)
        self.assertTrue(self.handle(suggestion.group(1)).startswith("Paper order filled: "))

    def test_saved_portfolios(self):
        item = papertrade.market().instruments[0]
        self.memory.set(KEY, {"cash": 500, "positions": {item.symbol: {"quantity": 2, "averagePrice": 1.5}}})
        kept = self.handle("show my paper portfolio")
        self.assertIn(f"- {item.symbol} (", kept)
        self.assertNotIn(FRESH, kept)
        self.assertIn(" Cleared 1 position.", self.handle("reset my paper portfolio"))
        self.memory.set(KEY, {"cash": -5, "positions": {}})
        self.assertIn(FRESH, self.handle("show my paper portfolio"))

    def test_a_real_trade_is_refused(self):
        item = papertrade.market().instruments[0]
        reply = self.handle(f"buy 10 shares of {item.symbol}")
        self.assertEqual(reply.splitlines()[:2], [
            REFUSAL, f"- To practise with demo money instead, say: paper buy 10 {item.symbol}",
        ])
        self.assertIsNone(self.memory.get(KEY))


if __name__ == "__main__":
    unittest.main()
