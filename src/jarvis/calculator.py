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


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        left = _evaluate(node.left)
        right = _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise CalculationError("That exponent is too large for me to compute.")
        try:
            return _BINARY_OPS[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise CalculationError("I cannot divide by zero.") from exc
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_evaluate(node.operand))
    raise CalculationError("Only basic arithmetic expressions are supported.")
