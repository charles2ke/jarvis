"""Safe arithmetic evaluation for the calculator skill.

:func:`calculate` accepts Python-style arithmetic plus the notation people
type: ``^`` for powers, ``×`` and ``÷``, ``²`` and ``³``, ``√``, and words such
as ``squared``, ``cubed``, ``to the power of`` and ``square root of``. Only
numbers, arithmetic operators and the ``sqrt`` and ``cbrt`` functions are
evaluated; anything else is rejected without using :func:`eval`.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from typing import Callable, Dict, Type, Union


_BINARY_OPS: Dict[Type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS: Dict[Type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

MAX_EXPONENT = 128
MAX_RESULT_BITS = 4096

Number = Union[int, float]


class CalculationError(ValueError):
    """Raised when an expression cannot be evaluated safely."""


def _integer_root(value: int, degree: int) -> int:
    """Return the largest integer whose ``degree``-th power is at most ``value``."""

    if value < 2:
        return value
    guess = 1 << -(-value.bit_length() // degree)
    while True:
        better = ((degree - 1) * guess + value // guess ** (degree - 1)) // degree
        if better >= guess:
            return guess
        guess = better


def _as_exact_int(value: Number) -> Number:
    if isinstance(value, float) and value.is_integer() and abs(value) < 2**53:
        return int(value)
    return value


def _sqrt(value: Number) -> Number:
    value = _as_exact_int(value)
    if value < 0:
        raise CalculationError("A negative number has no real square root.")
    if isinstance(value, int):
        root = math.isqrt(value)
        if root * root == value:
            return root
    return math.sqrt(value)


def _cbrt(value: Number) -> Number:
    value = _as_exact_int(value)
    sign = -1 if value < 0 else 1
    if isinstance(value, int):
        root = _integer_root(abs(value), 3)
        if root**3 == abs(value):
            return sign * root
    return sign * abs(value) ** (1 / 3)


_FUNCTIONS: Dict[str, Callable[[Number], Number]] = {"sqrt": _sqrt, "cbrt": _cbrt}

_ORDINAL_POWER = r"(?P<power>\d+)(?:st|nd|rd|th)"
_OPERAND = r"(-?\d+(?:\.\d+)?|\([^()]*\))"
_REWRITES = (
    (re.compile(r"(?<=\d),(?=\d{3}(?!\d))"), ""),
    (re.compile(r"[×✕✖⋅·]"), "*"),
    (re.compile(r"÷"), "/"),
    (re.compile(r"[−–]"), "-"),
    (re.compile(r"\^"), "**"),
    (re.compile(r"²"), "**2"),
    (re.compile(r"³"), "**3"),
    # "3 x 4" multiplies, but a hexadecimal literal such as 0x1F is left alone.
    (re.compile(r"(?<=[\d)\s])(?<!\b0)x(?=[\s\d(])", re.IGNORECASE), "*"),
    (re.compile(r"\bmod(?:ulo)?\b", re.IGNORECASE), "%"),
    (re.compile(r"\s*\bsquared\b", re.IGNORECASE), "**2"),
    (re.compile(r"\s*\bcubed\b", re.IGNORECASE), "**3"),
    (re.compile(r"\bto\s+the\s+" + _ORDINAL_POWER + r"\s+power\b", re.IGNORECASE), r"**\g<power>"),
    (
        re.compile(r"\b(?:raised\s+)?to\s+the\s+power\s+(?:of\s+)?|\braised\s+to\s+", re.IGNORECASE),
        "**",
    ),
    (re.compile(r"(?:\bthe\s+)?\bsquare\s+root\s+of\s+", re.IGNORECASE), "√"),
    (re.compile(r"(?:\bthe\s+)?\bcube\s+root\s+of\s+", re.IGNORECASE), "∛"),
    (re.compile(r"\b(sqrt|cbrt)\b", re.IGNORECASE), lambda found: found.group(1).lower()),
)
_ROOT_SIGNS = (("√", "sqrt"), ("∛", "cbrt"))


def normalize_expression(expression: str) -> str:
    """Rewrite friendly notation in ``expression`` as Python arithmetic."""

    text = expression
    for pattern, replacement in _REWRITES:
        text = pattern.sub(replacement, text)
    for sign, name in _ROOT_SIGNS:
        text = re.sub(re.escape(sign) + r"\s*" + _OPERAND, name + r"(\1)", text)
        text = text.replace(sign, name)
    return re.sub(r"\b(sqrt|cbrt)\s+" + _OPERAND, r"\1(\2)", text)


def calculate(expression: str) -> Number:
    """Evaluate a numeric expression without using :func:`eval`."""

    source = normalize_expression(expression).strip()
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:  # pragma: no cover - message varies by version
        raise CalculationError(f"I could not parse '{expression}'.") from exc
    return _evaluate(tree.body)


def format_number(value: Number) -> str:
    """Return ``value`` without floating point noise, such as ``0.3`` for 0.1 + 0.2."""

    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return f"{value:.15g}"
    return str(value)


def _evaluate(node: ast.AST, limit: float | None = None) -> Number:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return _check_result(node.value, limit)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        if isinstance(node.op, ast.Pow):
            right = _evaluate(node.right, MAX_EXPONENT)
            left = _evaluate(node.left, limit)
            if (
                isinstance(left, int)
                and isinstance(right, int)
                and right >= 0
                and (abs(left).bit_length() - 1) * right >= MAX_RESULT_BITS
            ):
                raise CalculationError("That result is too large for me to compute.")
        else:
            left = _evaluate(node.left, limit)
            right = _evaluate(node.right, limit)
        try:
            result = _BINARY_OPS[type(node.op)](left, right)
        except (OverflowError, ZeroDivisionError) as exc:
            if isinstance(exc, ZeroDivisionError):
                raise CalculationError("I cannot divide by zero.") from exc
            raise CalculationError("That result is too large for me to compute.") from exc
        return _check_result(result, limit)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _check_result(
            _UNARY_OPS[type(node.op)](_evaluate(node.operand, limit)), limit
        )
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCTIONS
        and len(node.args) == 1
        and not node.keywords
        and not isinstance(node.args[0], ast.Starred)
    ):
        argument = _evaluate(node.args[0])
        try:
            result = _FUNCTIONS[node.func.id](argument)
        except OverflowError as exc:
            raise CalculationError("That result is too large for me to compute.") from exc
        return _check_result(result, limit)
    raise CalculationError("Only basic arithmetic expressions are supported.")


def _check_result(result: Number, limit: float | None = None) -> Number:
    if isinstance(result, complex):
        raise CalculationError("That has no real-number answer.")
    if limit is not None and abs(result) > limit:
        raise CalculationError("That exponent is too large for me to compute.")
    if isinstance(result, int) and result.bit_length() > MAX_RESULT_BITS:
        raise CalculationError("That result is too large for me to compute.")
    if isinstance(result, float) and not math.isfinite(result):
        raise CalculationError("That result is too large for me to compute.")
    return result
