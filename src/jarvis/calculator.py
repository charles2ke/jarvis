"""Safe arithmetic evaluation for the calculator skill."""

from __future__ import annotations

import ast
import operator
from typing import Callable, Dict, Type


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


class CalculationError(ValueError):
    """Raised when an expression cannot be evaluated safely."""


def calculate(expression: str) -> float:
    """Evaluate a numeric expression without using :func:`eval`."""

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:  # pragma: no cover - message varies by version
        raise CalculationError(f"I could not parse '{expression}'.") from exc
    return _evaluate(tree.body)


def _evaluate(node: ast.AST, limit: float | None = None) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        result = node.value
        if limit is not None and abs(result) > limit:
            raise CalculationError("That exponent is too large for me to compute.")
        return result
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        if isinstance(node.op, ast.Pow):
            right = _evaluate(node.right, MAX_EXPONENT)
            left = _evaluate(node.left, limit)
        else:
            left = _evaluate(node.left, limit)
            right = _evaluate(node.right, limit)
        try:
            result = _BINARY_OPS[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise CalculationError("I cannot divide by zero.") from exc
        if limit is not None and abs(result) > limit:
            raise CalculationError("That exponent is too large for me to compute.")
        return result
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        result = _UNARY_OPS[type(node.op)](_evaluate(node.operand, limit))
        if limit is not None and abs(result) > limit:
            raise CalculationError("That exponent is too large for me to compute.")
        return result
    raise CalculationError("Only basic arithmetic expressions are supported.")
