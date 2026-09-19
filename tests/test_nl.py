"""Tests for natural language to text helpers and the number-words skill."""

import unittest

from jarvis import Assistant
from jarvis.memory import Memory
from jarvis.nl import flatten, normalize, number_to_words, words_to_number


class NumberToWordsTest(unittest.TestCase):
    def test_small_numbers(self) -> None:
        self.assertEqual(number_to_words(0), "zero")
        self.assertEqual(number_to_words(7), "seven")
        self.assertEqual(number_to_words(19), "nineteen")

    def test_tens_and_hundreds(self) -> None:
        self.assertEqual(number_to_words(42), "forty-two")
        self.assertEqual(number_to_words(70), "seventy")
        self.assertEqual(number_to_words(105), "one hundred and five")
        self.assertEqual(number_to_words(250), "two hundred and fifty")

    def test_large_numbers(self) -> None:
        self.assertEqual(number_to_words(1000), "one thousand")
        self.assertEqual(number_to_words(1005), "one thousand and five")
        self.assertEqual(number_to_words(1_000_000), "one million")
        self.assertEqual(
            number_to_words(1234),
            "one thousand two hundred and thirty-four",
        )

    def test_negative_numbers(self) -> None:
        self.assertEqual(number_to_words(-3), "minus three")

    def test_too_large(self) -> None:
        with self.assertRaises(ValueError):
            number_to_words(10 ** 20)


class WordsToNumberTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        for value in (0, 7, 42, 105, 250, 1005, 1234, 1_000_000):
            self.assertEqual(words_to_number(number_to_words(value)), value)

    def test_hyphenated_and_spaced(self) -> None:
        self.assertEqual(words_to_number("twenty-one"), 21)
        self.assertEqual(words_to_number("twenty one"), 21)
        self.assertEqual(words_to_number("one hundred and five"), 105)

    def test_negative(self) -> None:
        self.assertEqual(words_to_number("minus three"), -3)

    def test_rejects_non_numbers(self) -> None:
        self.assertIsNone(words_to_number("tell me a joke"))
        self.assertIsNone(words_to_number(""))
        self.assertIsNone(words_to_number("and"))


class FlattenTest(unittest.TestCase):
    def test_collapses_newlines_and_escapes(self) -> None:
        self.assertEqual(flatten("calculate\n   21 *\n 2"), "calculate 21 * 2")
        self.assertEqual(flatten(r"calculate\n21 * 2"), "calculate 21 * 2")

    def test_normalizes_smart_characters(self) -> None:
        self.assertEqual(flatten("what\u2019s the time"), "what's the time")

    def test_handles_empty(self) -> None:
        self.assertEqual(flatten(""), "")


class NormalizeTest(unittest.TestCase):
    def test_strips_polite_wrappers(self) -> None:
        self.assertEqual(normalize("Jarvis, please tell me a joke"), "tell me a joke")
        self.assertEqual(normalize("could you tell me a story please"), "tell me a story")

    def test_rewrites_numbers_and_operators(self) -> None:
        self.assertEqual(normalize("what is twenty one times two"), "what is 21 * 2")
        self.assertEqual(normalize("what is two hundred divided by four"), "what is 200 / 4")
        self.assertEqual(normalize("what is negative three times two"), "what is -3 * 2")
        self.assertEqual(normalize("what is three minus two"), "what is 3 - 2")

    def test_leaves_plain_commands_alone(self) -> None:
        self.assertEqual(normalize("calculate 21 * 2"), "calculate 21 * 2")


class NumberWordsSkillTest(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = Assistant(memory=Memory(None))

    def test_spell_out(self) -> None:
        self.assertEqual(self.assistant.respond("spell out 42"), "42 in words is forty-two.")
        self.assertEqual(self.assistant.respond("42 in words"), "42 in words is forty-two.")
        self.assertEqual(
            self.assistant.respond("how do you spell 1005"),
            "1005 in words is one thousand and five.",
        )

    def test_to_digits(self) -> None:
        self.assertEqual(
            self.assistant.respond("forty-two in digits"),
            "forty-two in digits is 42.",
        )
        self.assertEqual(
            self.assistant.respond("write one hundred and five in digits"),
            "one hundred and five in digits is 105.",
        )

    def test_unspellable_number(self) -> None:
        self.assertIn("too large", self.assistant.respond("spell out 12345678901234567890"))

    def test_calculator_still_wins(self) -> None:
        self.assertEqual(self.assistant.respond("calculate 21 * 2"), "21 * 2 = 42")


class AssistantNormalizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = Assistant(memory=Memory(None))

    def test_multiline_input_is_flattened(self) -> None:
        self.assertEqual(self.assistant.respond("calculate\n  21 *\n 2"), "21 * 2 = 42")

    def test_worded_arithmetic(self) -> None:
        self.assertEqual(self.assistant.respond("what is twenty one times two"), "21 * 2 = 42")
        self.assertEqual(self.assistant.respond("what is negative three times two"), "-3 * 2 = -6")

    def test_existing_routing_is_unchanged(self) -> None:
        self.assertIn("Gravity", self.assistant.respond("what is gravity?"))
        self.assertIn("Hello", self.assistant.respond("hello"))
        self.assertIn("Tokyo", self.assistant.respond("what is the capital of Japan?"))


class CloudAnswerPhrasingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = Assistant(memory=Memory(None))

    def _query_for(self, message: str) -> str:
        resolved = self.assistant.registry.resolve(message)
        self.assertIsNotNone(resolved)
        skill, match = resolved
        self.assertEqual(skill.name, "answer")
        return match.group("query")

    def test_plain_text_phrasings(self) -> None:
        self.assertEqual(
            self._query_for("answer in plain text: who owns the CLI?"),
            "who owns the CLI?",
        )
        self.assertEqual(
            self._query_for("give me a text answer to what memory.py persists"),
            "what memory.py persists",
        )
        self.assertEqual(
            self._query_for("turn this into text: how does routing work?"),
            "how does routing work?",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
