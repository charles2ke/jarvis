"""Unit conversion helpers for the unit-conversion skill."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, Iterable, List, Tuple


class ConversionError(ValueError):
    """Raised when a conversion cannot be performed."""


@dataclass(frozen=True)
class Unit:
    """A unit of measurement expressed relative to its family's base unit."""

    name: str
    plural: str
    family: str
    factor: float
    offset: float = 0.0

    def to_base(self, value: float) -> float:
        return value * self.factor + self.offset

    def from_base(self, value: float) -> float:
        return (value - self.offset) / self.factor


# Each family converts through a base unit: metres, kilograms, litres, seconds,
# degrees Celsius, metres per second and square metres respectively.
_UNITS: Tuple[Tuple[Unit, Tuple[str, ...]], ...] = (
    # Length (base: metre)
    (Unit("millimetre", "millimetres", "length", 0.001),
     ("mm", "millimeter", "millimeters", "millimetre", "millimetres")),
    (Unit("centimetre", "centimetres", "length", 0.01),
     ("cm", "centimeter", "centimeters", "centimetre", "centimetres")),
    (Unit("metre", "metres", "length", 1.0),
     ("m", "meter", "meters", "metre", "metres")),
    (Unit("kilometre", "kilometres", "length", 1000.0),
     ("km", "kilometer", "kilometers", "kilometre", "kilometres")),
    (Unit("inch", "inches", "length", 0.0254),
     ("in", "inch", "inches")),
    (Unit("foot", "feet", "length", 0.3048),
     ("ft", "foot", "feet")),
    (Unit("yard", "yards", "length", 0.9144),
     ("yd", "yard", "yards")),
    (Unit("mile", "miles", "length", 1609.344),
     ("mi", "mile", "miles")),
    (Unit("nautical mile", "nautical miles", "length", 1852.0),
     ("nmi", "nautical mile", "nautical miles", "sea mile", "sea miles")),
    # Mass (base: kilogram)
    (Unit("milligram", "milligrams", "mass", 0.000001),
     ("mg", "milligram", "milligrams", "milligramme", "milligrammes")),
    (Unit("gram", "grams", "mass", 0.001),
     ("g", "gram", "grams", "gramme", "grammes")),
    (Unit("kilogram", "kilograms", "mass", 1.0),
     ("kg", "kilo", "kilos", "kilogram", "kilograms", "kilogramme", "kilogrammes")),
    (Unit("tonne", "tonnes", "mass", 1000.0),
     ("t", "tonne", "tonnes", "metric ton", "metric tons")),
    (Unit("ounce", "ounces", "mass", 0.028349523125),
     ("oz", "ounce", "ounces")),
    (Unit("pound", "pounds", "mass", 0.45359237),
     ("lb", "lbs", "pound", "pounds")),
    (Unit("stone", "stone", "mass", 6.35029318),
     ("st", "stone", "stones")),
    # Volume (base: litre)
    (Unit("millilitre", "millilitres", "volume", 0.001),
     ("ml", "milliliter", "milliliters", "millilitre", "millilitres")),
    (Unit("litre", "litres", "volume", 1.0),
     ("l", "liter", "liters", "litre", "litres")),
    (Unit("US cup", "US cups", "volume", 0.2365882365),
     ("cup", "cups", "us cup", "us cups")),
    (Unit("US pint", "US pints", "volume", 0.473176473),
     ("pt", "pint", "pints", "us pint", "us pints")),
    (Unit("US gallon", "US gallons", "volume", 3.785411784),
     ("gal", "gallon", "gallons", "us gallon", "us gallons")),
    (Unit("imperial pint", "imperial pints", "volume", 0.56826125),
     ("imperial pint", "imperial pints", "uk pint", "uk pints")),
    (Unit("imperial gallon", "imperial gallons", "volume", 4.54609),
     ("imperial gallon", "imperial gallons", "uk gallon", "uk gallons")),
    # Time (base: second)
    (Unit("second", "seconds", "time", 1.0),
     ("s", "sec", "secs", "second", "seconds")),
    (Unit("minute", "minutes", "time", 60.0),
     ("min", "mins", "minute", "minutes")),
    (Unit("hour", "hours", "time", 3600.0),
     ("h", "hr", "hrs", "hour", "hours")),
    (Unit("day", "days", "time", 86400.0),
     ("d", "day", "days")),
    (Unit("week", "weeks", "time", 604800.0),
     ("wk", "week", "weeks")),
    # Temperature (base: degree Celsius)
    (Unit("degree Celsius", "degrees Celsius", "temperature", 1.0),
     ("c", "celsius", "centigrade", "degree celsius", "degrees celsius")),
    (Unit("degree Fahrenheit", "degrees Fahrenheit", "temperature", 5.0 / 9.0,
          -32.0 * 5.0 / 9.0),
     ("f", "fahrenheit", "degree fahrenheit", "degrees fahrenheit")),
    (Unit("kelvin", "kelvin", "temperature", 1.0, -273.15),
     ("k", "kelvin", "kelvins")),
    # Speed (base: metre per second)
    (Unit("metre per second", "metres per second", "speed", 1.0),
     ("m/s", "mps", "metre per second", "metres per second",
      "meter per second", "meters per second")),
    (Unit("kilometre per hour", "kilometres per hour", "speed", 1000.0 / 3600.0),
     ("kph", "km/h", "kmh", "kilometre per hour", "kilometres per hour",
      "kilometer per hour", "kilometers per hour")),
    (Unit("mile per hour", "miles per hour", "speed", 1609.344 / 3600.0),
     ("mph", "mi/h", "mile per hour", "miles per hour")),
    (Unit("knot", "knots", "speed", 1852.0 / 3600.0),
     ("kn", "kt", "kts", "knot", "knots")),
    # Area (base: square metre)
    (Unit("square metre", "square metres", "area", 1.0),
     ("m2", "sqm", "square meter", "square meters", "square metre",
      "square metres")),
    (Unit("square kilometre", "square kilometres", "area", 1_000_000.0),
     ("km2", "sqkm", "square kilometer", "square kilometers",
      "square kilometre", "square kilometres")),
    (Unit("square foot", "square feet", "area", 0.09290304),
     ("sqft", "ft2", "square foot", "square feet")),
    (Unit("acre", "acres", "area", 4046.8564224),
     ("acre", "acres")),
    (Unit("hectare", "hectares", "area", 10_000.0),
     ("ha", "hectare", "hectares")),
    (Unit("square mile", "square miles", "area", 2_589_988.110336),
     ("sqmi", "mi2", "square mile", "square miles")),
)


def _build_aliases() -> Dict[str, Unit]:
    aliases: Dict[str, Unit] = {}
    for unit, names in _UNITS:
        for name in names:
            aliases.setdefault(name, unit)
    return aliases


_ALIASES: Dict[str, Unit] = _build_aliases()

#: Unit spellings the skill's patterns accept, longest first so that
#: multi-word names such as "nautical mile" win over "mile".
UNIT_NAMES: Tuple[str, ...] = tuple(
    sorted(_ALIASES, key=lambda name: (-len(name), name))
)


def _normalise(name: str) -> str:
    cleaned = " ".join(name.strip().lower().replace("°", " ").split())
    if cleaned.startswith("degrees "):
        cleaned = cleaned[len("degrees ") :]
    elif cleaned.startswith("degree "):
        cleaned = cleaned[len("degree ") :]
    return cleaned


def find_unit(name: str) -> Unit:
    """Return the unit registered under ``name``."""

    cleaned = _normalise(name)
    unit = _ALIASES.get(cleaned)
    if unit is None and cleaned.endswith("s"):
        unit = _ALIASES.get(cleaned[:-1])
    if unit is None:
        raise ConversionError(f"I do not know the unit '{name.strip()}'.")
    return unit


def convert(value: float, source: str, target: str) -> float:
    """Convert ``value`` from the ``source`` unit into the ``target`` unit."""

    if not math.isfinite(value):
        raise ConversionError("That value is too large for me to convert.")
    from_unit = find_unit(source)
    to_unit = find_unit(target)
    if from_unit.family != to_unit.family:
        raise ConversionError(
            f"I cannot convert {from_unit.family} into {to_unit.family}."
        )
    result = to_unit.from_base(from_unit.to_base(value))
    if not math.isfinite(result):
        raise ConversionError("That value is too large for me to convert.")
    return result


def format_quantity(value: float, unit: Unit) -> str:
    """Render ``value`` with a sensible precision and the unit's name."""

    if not math.isfinite(value):
        raise ConversionError("That value is too large for me to convert.")
    rounded = round(value, 4)
    if rounded == int(rounded):
        text = str(int(rounded))
    else:
        text = f"{rounded:g}"
    name = unit.name if abs(rounded) == 1 else unit.plural
    return f"{text} {name}"


def describe_conversion(value: float, source: str, target: str) -> str:
    """Return a sentence describing a conversion."""

    result = convert(value, source, target)
    return (
        f"{format_quantity(value, find_unit(source))} = "
        f"{format_quantity(result, find_unit(target))}."
    )


def families() -> Dict[str, List[str]]:
    """Map each family name to its canonical unit names."""

    grouped: Dict[str, List[str]] = {}
    for unit, _names in _UNITS:
        grouped.setdefault(unit.family, []).append(unit.name)
    return grouped


def describe_units(names: Iterable[str] = ()) -> str:
    """Summarise the supported unit families."""

    grouped = families()
    selected = list(names) or list(grouped)
    lines = ["I can convert between these units:"]
    for family in selected:
        units = grouped.get(family)
        if units:
            lines.append(f"- {family}: {', '.join(units)}")
    return "\n".join(lines)
