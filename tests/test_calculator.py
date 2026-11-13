import unittest

from jarvis.calculator import CalculationError, calculate, format_number


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

    def test_rejects_oversized_result(self):
        with self.assertRaises(CalculationError):
            calculate("((10 ** 128) ** 128) ** 128")

    def test_rejects_booleans(self):
        for expression in ("True", "False", "True + 1"):
            with self.assertRaises(CalculationError):
                calculate(expression)

    def test_rejects_invalid_syntax(self):
        with self.assertRaises(CalculationError):
            calculate("1 +")

    def test_everyday_notation(self):
        cases = {
            "2^10": 1024,
            "3 squared": 9,
            "4 cubed": 64,
            "2³": 8,
            "2 to the power of 10": 1024,
            "2 to the 3rd power": 8,
            "5 x 6": 30,
            "12 × 3": 36,
            "100 ÷ 8": 12.5,
            "17 mod 5": 2,
            "1,000,000 / 4": 250000,
            "0x10": 16,
        }
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(calculate(expression), expected)

    def test_square_and_cube_roots(self):
        cases = {
            "square root of 144": 12,
            "the cube root of 27": 3,
            "cube root of -8": -2,
            "√81": 9,
            "∛64": 4,
            "SQRT(16) + 1": 5,
        }
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                self.assertEqual(calculate(expression), expected)
        self.assertEqual(calculate("sqrt(10 ** 40)"), 10 ** 20)  # exact, not a float

    def test_rejects_answers_that_are_not_real_numbers(self):
        for expression in ("sqrt(-4)", "(-8) ** 0.5"):
            with self.subTest(expression=expression), self.assertRaises(CalculationError):
                calculate(expression)

    def test_only_whitelisted_single_argument_calls(self):
        for expression in ("sqrt(16, 2)", "sqrt(x=4)", "sqrt(*[4])", "abs(-1)", "sqrt"):
            with self.subTest(expression=expression), self.assertRaises(CalculationError):
                calculate(expression)

    def test_format_number(self):
        self.assertEqual(format_number(0.1 + 0.2), "0.3")
        self.assertEqual(format_number(2.0), "2")
        self.assertEqual(format_number(10 / 3), "3.33333333333333")
        self.assertEqual(format_number(1e20), "1e+20")


if __name__ == "__main__":
    unittest.main()
