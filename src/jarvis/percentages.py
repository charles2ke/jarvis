"""Percentage questions answered with exact decimal arithmetic.

Each function takes the numbers as typed (``"1,250.50"``) plus an optional
currency symbol and returns a one-line reply, for example
``percent_of("15", "80")`` gives ``"15% of 80 is 12."``. Results that had to
be rounded say "about"; money is shown to two decimal places.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

__all__ = [
    "CURRENCY",
    "NUMBER",
    "PercentError",
    "change_by",
    "discount",
    "percent_change",
    "percent_of",
    "tip",
    "what_percent",
]

#: A number as people type it: ``12``, ``-3.5``, ``.5`` or ``1,250,000.75``.
NUMBER = r"[-+]?(?:(?:\d{1,3}(?:,\d{3})+(?![\d,])|\d+)(?:\.\d+)?|\.\d+)"
#: A currency symbol that may come before an amount.
CURRENCY = r"[$£€¥₹]"

_LIMIT = Decimal(10) ** 30


class PercentError(ValueError):
    """Raised when a percentage cannot be worked out."""


def _number(text: str) -> Decimal:
    try:
        value = Decimal((text or "").replace(",", "").strip())
    except InvalidOperation as exc:
        raise PercentError(f"I could not read the number '{text}'.") from exc
    if not value.is_finite() or abs(value) >= _LIMIT:
        raise PercentError("Those numbers are too large for me to work with.")
    return value


def _show(value: Decimal, currency: str = "", places: int = 6) -> str:
    """Return ``value`` rounded for display, prefixed with 'about' if rounding changed it."""

    places = 2 if currency else places
    with localcontext() as context:
        context.prec = 80
        rounded = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
        whole = rounded == rounded.to_integral_value()
        if currency and not whole:
            digits = f"{abs(rounded):,.2f}"
        else:
            digits = f"{abs(rounded).normalize():,f}"
    sign = "-" if rounded < 0 else ""
    about = "about " if rounded != value else ""
    return f"{about}{sign}{currency}{digits}"


def _plain(value: Decimal, currency: str = "") -> str:
    """Return a number the user typed, tidied but never rounded."""

    shown = _show(value, currency, places=12)
    return shown[len("about "):] if shown.startswith("about ") else shown


def _percent(value: Decimal) -> str:
    return _show(value, places=2) + "%"


def _calc(compute):
    with localcontext() as context:
        context.prec = 60
        return compute()


def percent_of(percent: str, amount: str, currency: str = "") -> str:
    """Reply to 'what is ``percent``% of ``amount``'."""

    rate, base = _number(percent), _number(amount)
    result = _calc(lambda: rate * base / 100)
    return f"{_plain(rate)}% of {_plain(base, currency)} is {_show(result, currency)}."


def what_percent(part: str, whole: str, currency: str = "") -> str:
    """Reply to '``part`` is what percent of ``whole``'."""

    piece, total = _number(part), _number(whole)
    if total == 0:
        raise PercentError("I cannot work out a percentage of zero.")
    result = _calc(lambda: piece / total * 100)
    return (
        f"{_plain(piece, currency)} is {_percent(result)} of "
        f"{_plain(total, currency)}."
    )


def change_by(amount: str, percent: str, increase: bool, currency: str = "") -> str:
    """Reply to 'increase ``amount`` by ``percent``%' or the decrease."""

    base, rate = _number(amount), _number(percent)
    delta = _calc(lambda: base * rate / 100)
    result = _calc(lambda: base + delta if increase else base - delta)
    verb = "increased" if increase else "decreased"
    return (
        f"{_plain(base, currency)} {verb} by {_plain(rate)}% is "
        f"{_show(result, currency)} (a change of {_show(abs(delta), currency)})."
    )


def discount(percent: str, amount: str, currency: str = "") -> str:
    """Reply to 'what is ``percent``% off ``amount``'."""

    rate, base = _number(percent), _number(amount)
    saving = _calc(lambda: base * rate / 100)
    result = _calc(lambda: base - saving)
    return (
        f"{_plain(rate)}% off {_plain(base, currency)} is {_show(result, currency)}, "
        f"a saving of {_show(saving, currency)}."
    )


def tip(percent: str, amount: str, currency: str = "") -> str:
    """Reply to 'what is a ``percent``% tip on ``amount``'."""

    rate, base = _number(percent), _number(amount)
    gratuity = _calc(lambda: base * rate / 100)
    total = _calc(lambda: base + gratuity)
    return (
        f"A tip of {_plain(rate)}% on {_plain(base, currency)} is "
        f"{_show(gratuity, currency)}, making {_show(total, currency)} in total."
    )


def percent_change(start: str, end: str, currency: str = "") -> str:
    """Reply to 'what is the percentage change from ``start`` to ``end``'."""

    first, second = _number(start), _number(end)
    if first == 0:
        raise PercentError("I cannot work out a percentage change from zero.")
    if first == second:
        return f"From {_plain(first, currency)} to {_plain(second, currency)} there is no change."
    result = _calc(lambda: (second - first) / abs(first) * 100)
    kind = "an increase" if result > 0 else "a decrease"
    return (
        f"From {_plain(first, currency)} to {_plain(second, currency)} is {kind} "
        f"of {_percent(abs(result))}."
    )
