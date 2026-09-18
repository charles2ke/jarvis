import unittest

from jarvis.calculator import CalculationError, calculate


class CalculatorTests(unittest.TestCase):
    def test_basic_operations(self):
        self.assertEqual(calculate("1 + 2 * 3"), 7)
        self.assertEqual(calculate("(1 + 2) * 3"), 9)
        self.assertEqual(calculate("-4"), -4)
        self.assertEqual(calculate("7 % 4"), 3)

    def test_division_by_zero(self):
        with self.assertRaises(CalculationError):
            calculate("1 / 0")

    def test_rejects_names_and_calls(self):
        for expression in ("__import__('os').system('ls')", "open('x')", "a + 1"):
            with self.assertRaises(CalculationError):
                calculate(expression)

    def test_rejects_huge_exponent(self):
        with self.assertRaises(CalculationError):
            calculate("9 ** 10000")

    def test_rejects_huge_nested_exponent_before_evaluation(self):
        with self.assertRaises(CalculationError):
            calculate("2 ** (2 ** 1000000)")

    def test_rejects_invalid_syntax(self):
        with self.assertRaises(CalculationError):
            calculate("1 +")


if __name__ == "__main__":
    unittest.main()
