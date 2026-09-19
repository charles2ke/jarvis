"""Step-by-step solvers for maths, physics, chemistry and biology problems.

Everything here is dependency free and deterministic: each solver parses the
question with regular expressions, performs the calculation and returns a short
worked answer. :func:`solve_problem` picks the first solver that understands the
question and returns ``None`` when none of them do.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple

NUMBER = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

_TOLERANCE = 1e-9


def _fmt(value: float) -> str:
    """Format a number for display without noisy floating point tails."""

    if isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
        if abs(value) < 1e16:
            return str(int(value))
    return f"{value:.6g}"


# ---------------------------------------------------------------------------
# Mathematics: equation solving
# ---------------------------------------------------------------------------

_BINARY_OPS: Dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}

_UNARY_OPS: Dict[type, Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

MAX_EXPONENT = 8


class ScienceError(ValueError):
    """Raised when a question is understood but cannot be solved."""


def _normalise_expression(expression: str) -> str:
    text = expression.replace("^", "**").replace("×", "*").replace("÷", "/")
    text = re.sub(r"(\d)\s*([a-z])", r"\1*\2", text)
    text = re.sub(r"(\d|[a-z])\s*\(", r"\1*(", text)
    text = re.sub(r"\)\s*(\d|[a-z]|\()", r")*\1", text)
    text = re.sub(r"([a-z])\s+([a-z])", r"\1*\2", text)
    return text


def _eval_expression(node: ast.AST, variable: str, value: float) -> float:
    if isinstance(node, ast.Expression):
        return _eval_expression(node.body, variable, value)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        if isinstance(node.value, bool):
            raise ScienceError("I can only work with numbers here.")
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id != variable:
            raise ScienceError(
                f"I can only solve for one unknown at a time, and '{node.id}' is extra."
            )
        return value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_expression(node.operand, variable, value))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        left = _eval_expression(node.left, variable, value)
        right = _eval_expression(node.right, variable, value)
        if isinstance(node.op, ast.Pow):
            if not float(right).is_integer() or abs(right) > MAX_EXPONENT:
                raise ScienceError("I only handle small whole-number powers.")
        try:
            return _BINARY_OPS[type(node.op)](left, right)
        except ZeroDivisionError as exc:
            raise ScienceError("That expression divides by zero.") from exc
        except OverflowError as exc:
            raise ScienceError("Those numbers are too large for me.") from exc
    raise ScienceError("I could not read that expression.")


def _polynomial_value(expression: str, variable: str, value: float) -> float:
    try:
        tree = ast.parse(_normalise_expression(expression), mode="eval")
    except SyntaxError as exc:
        raise ScienceError(f"I could not parse '{expression.strip()}'.") from exc
    return _eval_expression(tree, variable, value)


def _fit_polynomial(expression: str, variable: str) -> Tuple[float, float, float]:
    """Return ``(a, b, c)`` for ``a*x**2 + b*x + c`` fitted to ``expression``."""

    f0 = _polynomial_value(expression, variable, 0.0)
    f1 = _polynomial_value(expression, variable, 1.0)
    fm1 = _polynomial_value(expression, variable, -1.0)
    c = f0
    a = (f1 + fm1) / 2 - c
    b = (f1 - fm1) / 2
    for probe in (2.0, 3.5):
        expected = a * probe**2 + b * probe + c
        actual = _polynomial_value(expression, variable, probe)
        scale = max(1.0, abs(expected), abs(actual))
        if abs(expected - actual) > 1e-6 * scale:
            raise ScienceError(
                "I can only solve linear and quadratic equations for now."
            )
    return a, b, c


def _signed(value: float) -> str:
    """Render ``value`` as a signed term, e.g. ``- 8`` instead of ``+ -8``."""

    sign = "-" if value < 0 else "+"
    return f"{sign} {_fmt(abs(value))}"


def _clean(value: float) -> float:
    return 0.0 if abs(value) < 1e-12 else value


def solve_equation(text: str) -> Optional[str]:
    """Solve a linear or quadratic equation such as ``2x + 3 = 11``."""

    match = re.search(
        rf"(?:solve|find(?:\s+the)?\s+(?:value\s+of\s+)?)?\s*"
        rf"(?P<equation>[^=]*=[^=]*?)\s*(?:for\s+(?P<var>[a-z]))?\s*[.?!]?\s*$",
        text.strip(),
        re.IGNORECASE,
    )
    if match is None:
        return None
    equation = match.group("equation").lower()
    if equation.count("=") != 1:
        return None
    left, right = (side.strip() for side in equation.split("="))
    if not left or not right:
        return None
    variable = (match.group("var") or "").lower()
    if not variable:
        letters = sorted(set(re.findall(r"[a-z]", equation)))
        if len(letters) != 1:
            return None
        variable = letters[0]
    if variable not in equation:
        return None

    try:
        a, b, c = _fit_polynomial(f"({left}) - ({right})", variable)
    except ScienceError as exc:
        return str(exc)
    a, b, c = _clean(a), _clean(b), _clean(c)

    heading = f"Equation: {left} = {right}"
    if a == 0 and b == 0:
        if c == 0:
            return f"{heading}\nEvery value of {variable} satisfies this equation."
        return f"{heading}\nThere is no value of {variable} that satisfies this equation."
    if a == 0:
        root = -c / b
        return (
            f"{heading}\n"
            f"Rearranged: {_fmt(b)}{variable} {_signed(c)} = 0\n"
            f"{variable} = {_fmt(-c)} / {_fmt(b)}\n"
            f"{variable} = {_fmt(root)}"
        )
    discriminant = b * b - 4 * a * c
    lines = [
        heading,
        f"Rearranged: {_fmt(a)}{variable}^2 {_signed(b)}{variable} {_signed(c)} = 0",
        f"Discriminant b^2 - 4ac = {_fmt(discriminant)}",
    ]
    if discriminant < 0:
        real = -b / (2 * a)
        imaginary = math.sqrt(-discriminant) / (2 * a)
        lines.append(
            f"{variable} = {_fmt(real)} ± {_fmt(abs(imaginary))}i (no real solutions)"
        )
    elif discriminant == 0:
        lines.append(f"{variable} = {_fmt(-b / (2 * a))} (a repeated root)")
    else:
        root_term = math.sqrt(discriminant)
        first = (-b + root_term) / (2 * a)
        second = (-b - root_term) / (2 * a)
        lines.append(f"{variable} = {_fmt(first)} or {variable} = {_fmt(second)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Physics
# ---------------------------------------------------------------------------

GRAVITY = 9.81

_UNIT_QUANTITIES: Sequence[Tuple[str, str, float]] = (
    # (unit pattern, quantity, factor to SI)
    (r"km/h", "speed", 1 / 3.6),
    (r"m/s\s*(?:\^?2|²)", "acceleration", 1.0),
    (r"m/s", "speed", 1.0),
    (r"kg", "mass", 1.0),
    (r"grams?|g\b", "mass", 0.001),
    (r"km\b", "distance", 1000.0),
    (r"cm\b", "distance", 0.01),
    (r"metres?|meters?|m\b", "distance", 1.0),
    (r"seconds?|s\b", "time", 1.0),
    (r"minutes?|min\b", "time", 60.0),
    (r"hours?|h\b", "time", 3600.0),
    (r"newtons?|N\b", "force", 1.0),
    (r"joules?|J\b", "energy", 1.0),
    (r"watts?|W\b", "power", 1.0),
    (r"volts?|V\b", "voltage", 1.0),
    (r"amp(?:ere)?s?|A\b", "current", 1.0),
    (r"ohms?|Ω", "resistance", 1.0),
)

_QUANTITY_UNITS: Dict[str, str] = {
    "mass": "kg",
    "distance": "m",
    "time": "s",
    "speed": "m/s",
    "acceleration": "m/s^2",
    "force": "N",
    "energy": "J",
    "power": "W",
    "voltage": "V",
    "current": "A",
    "resistance": "Ω",
    "density": "kg/m^3",
    "volume": "m^3",
    "momentum": "kg·m/s",
    "height": "m",
    "work": "J",
    "pressure": "Pa",
    "area": "m^2",
}

_QUANTITY_ALIASES: Sequence[Tuple[str, str]] = (
    (r"kinetic energy", "energy"),
    (r"potential energy", "energy"),
    (r"velocity|speed", "speed"),
    (r"acceleration", "acceleration"),
    (r"distance|displacement|length", "distance"),
    (r"time|duration", "time"),
    (r"mass", "mass"),
    (r"height|altitude", "height"),
    (r"force", "force"),
    (r"work", "work"),
    (r"power", "power"),
    (r"voltage|potential difference", "voltage"),
    (r"current", "current"),
    (r"resistance", "resistance"),
    (r"volume", "volume"),
    (r"density", "density"),
    (r"area", "area"),
    (r"pressure", "pressure"),
    (r"momentum", "momentum"),
)


def _extract_quantities(text: str) -> Dict[str, float]:
    """Pull named or unit-tagged quantities out of a physics question."""

    found: Dict[str, float] = {}
    lowered = text.lower()

    for alias, quantity in _QUANTITY_ALIASES:
        pattern = rf"\b(?:{alias})\b(?:\s+(?:is|of|=|:|was))?\s*(?P<value>{NUMBER})"
        match = re.search(pattern, lowered)
        if match and quantity not in found:
            found[quantity] = float(match.group("value"))
        pattern_before = rf"(?P<value>{NUMBER})\s*(?:\w+\s+)?\b(?:{alias})\b"
        match = re.search(pattern_before, lowered)
        if match and quantity not in found:
            found[quantity] = float(match.group("value"))

    for unit, quantity, factor in _UNIT_QUANTITIES:
        if quantity in found:
            continue
        match = re.search(rf"(?P<value>{NUMBER})\s*(?:{unit})", text)
        if match:
            found[quantity] = float(match.group("value")) * factor
    return found


_PHYSICS_FORMULAS: Sequence[Tuple[str, str, Sequence[str], str, Callable[..., float]]] = (
    ("kinetic energy", "energy", ("mass", "speed"), "KE = ½ m v²",
     lambda mass, speed: 0.5 * mass * speed**2),
    ("potential energy", "energy", ("mass", "height"), "PE = m g h",
     lambda mass, height: mass * GRAVITY * height),
    ("momentum", "momentum", ("mass", "speed"), "p = m v",
     lambda mass, speed: mass * speed),
    ("force", "force", ("mass", "acceleration"), "F = m a",
     lambda mass, acceleration: mass * acceleration),
    ("weight", "force", ("mass",), "W = m g", lambda mass: mass * GRAVITY),
    ("speed", "speed", ("distance", "time"), "v = d / t",
     lambda distance, time: distance / time),
    ("acceleration", "acceleration", ("speed", "time"), "a = Δv / t",
     lambda speed, time: speed / time),
    ("distance", "distance", ("speed", "time"), "d = v t",
     lambda speed, time: speed * time),
    ("time", "time", ("distance", "speed"), "t = d / v",
     lambda distance, speed: distance / speed),
    ("density", "density", ("mass", "volume"), "ρ = m / V",
     lambda mass, volume: mass / volume),
    ("work", "work", ("force", "distance"), "W = F d",
     lambda force, distance: force * distance),
    ("power", "power", ("energy", "time"), "P = E / t",
     lambda energy, time: energy / time),
    ("pressure", "pressure", ("force", "area"), "P = F / A",
     lambda force, area: force / area),
    ("voltage", "voltage", ("current", "resistance"), "V = I R",
     lambda current, resistance: current * resistance),
    ("current", "current", ("voltage", "resistance"), "I = V / R",
     lambda voltage, resistance: voltage / resistance),
    ("resistance", "resistance", ("voltage", "current"), "R = V / I",
     lambda voltage, current: voltage / current),
)

_PHYSICS_TARGETS: Sequence[Tuple[str, str]] = (
    (r"kinetic energy", "kinetic energy"),
    (r"potential energy|gravitational energy", "potential energy"),
    (r"momentum", "momentum"),
    (r"weight", "weight"),
    (r"force", "force"),
    (r"speed|velocity|how fast", "speed"),
    (r"acceleration", "acceleration"),
    (r"density", "density"),
    (r"work done|work", "work"),
    (r"power", "power"),
    (r"pressure", "pressure"),
    (r"voltage|potential difference", "voltage"),
    (r"current", "current"),
    (r"resistance", "resistance"),
    (r"distance|how far", "distance"),
    (r"time|how long", "time"),
)


def solve_physics(text: str) -> Optional[str]:
    """Answer a one-formula physics question stated with numbers and units."""

    lowered = text.lower()
    if not re.search(r"\d", lowered):
        return None
    asked = re.search(
        r"\b(?:find|calculate|compute|work out|what(?:'s| is)|how (?:fast|far|long|much))\b",
        lowered,
    )
    if asked is None:
        return None
    tail = lowered[asked.start():]

    target: Optional[str] = None
    for pattern, name in _PHYSICS_TARGETS:
        if re.search(rf"\b(?:{pattern})\b", tail):
            target = name
            break
    if target is None:
        return None

    quantities = _extract_quantities(text)
    for name, produces, needs, formula, compute in _PHYSICS_FORMULAS:
        if name != target:
            continue
        if not all(need in quantities for need in needs):
            continue
        args = [quantities[need] for need in needs]
        if any(arg == 0 for arg, need in zip(args, needs) if need in {"time", "volume", "area", "current", "speed"}) and "/" in formula:
            return "I cannot divide by zero — please check the values."
        result = compute(*args)
        given = ", ".join(
            f"{need} = {_fmt(quantities[need])} {_QUANTITY_UNITS[need]}" for need in needs
        )
        return (
            f"Physics — {target}\n"
            f"Given: {given}\n"
            f"Formula: {formula}\n"
            f"Answer: {target} = {_fmt(result)} {_QUANTITY_UNITS[produces]}"
        )

    needed = next(
        (needs for name, _, needs, _, _ in _PHYSICS_FORMULAS if name == target), ()
    )
    if needed:
        missing = [need for need in needed if need not in quantities]
        if missing:
            return (
                f"To work out {target} I need {' and '.join(missing)}. "
                f"Try: 'calculate {target} with "
                + " and ".join(f"{need} 10 {_QUANTITY_UNITS[need]}" for need in needed)
                + "'."
            )
    return None


# ---------------------------------------------------------------------------
# Chemistry
# ---------------------------------------------------------------------------

_ATOMIC_WEIGHT_DATA = (
    "H:1.008 He:4.0026 Li:6.94 Be:9.0122 B:10.81 C:12.011 N:14.007 O:15.999 "
    "F:18.998 Ne:20.180 Na:22.990 Mg:24.305 Al:26.982 Si:28.085 P:30.974 "
    "S:32.06 Cl:35.45 Ar:39.948 K:39.098 Ca:40.078 Sc:44.956 Ti:47.867 "
    "V:50.942 Cr:51.996 Mn:54.938 Fe:55.845 Co:58.933 Ni:58.693 Cu:63.546 "
    "Zn:65.38 Ga:69.723 Ge:72.630 As:74.922 Se:78.971 Br:79.904 Kr:83.798 "
    "Rb:85.468 Sr:87.62 Y:88.906 Zr:91.224 Nb:92.906 Mo:95.95 Tc:98 "
    "Ru:101.07 Rh:102.91 Pd:106.42 Ag:107.87 Cd:112.41 In:114.82 Sn:118.71 "
    "Sb:121.76 Te:127.60 I:126.90 Xe:131.29 Cs:132.91 Ba:137.33 La:138.91 "
    "Ce:140.12 Pr:140.91 Nd:144.24 Pm:145 Sm:150.36 Eu:151.96 Gd:157.25 "
    "Tb:158.93 Dy:162.50 Ho:164.93 Er:167.26 Tm:168.93 Yb:173.05 Lu:174.97 "
    "Hf:178.49 Ta:180.95 W:183.84 Re:186.21 Os:190.23 Ir:192.22 Pt:195.08 "
    "Au:196.97 Hg:200.59 Tl:204.38 Pb:207.2 Bi:208.98 Po:209 At:210 Rn:222 "
    "Fr:223 Ra:226 Ac:227 Th:232.04 Pa:231.04 U:238.03"
)

ATOMIC_WEIGHTS: Dict[str, float] = {
    symbol: float(weight)
    for symbol, weight in (entry.split(":") for entry in _ATOMIC_WEIGHT_DATA.split())
}

GAS_CONSTANT = 0.082057  # L·atm/(mol·K)


def parse_formula(formula: str) -> Dict[str, int]:
    """Return the element counts for a chemical formula such as ``Ca(OH)2``."""

    tokens = re.findall(r"[A-Z][a-z]?|\d+|\(|\)", formula)
    if "".join(tokens) != formula.replace(" ", ""):
        raise ScienceError(f"'{formula}' does not look like a chemical formula.")
    counts: List[Dict[str, int]] = [{}]
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "(":
            counts.append({})
        elif token == ")":
            if len(counts) == 1:
                raise ScienceError(f"'{formula}' has unbalanced brackets.")
            group = counts.pop()
            multiplier = 1
            if index + 1 < len(tokens) and tokens[index + 1].isdigit():
                index += 1
                multiplier = int(tokens[index])
            for element, amount in group.items():
                counts[-1][element] = counts[-1].get(element, 0) + amount * multiplier
        elif token.isdigit():
            raise ScienceError(f"'{formula}' has a number without an element.")
        else:
            if token not in ATOMIC_WEIGHTS:
                raise ScienceError(f"I do not know the element '{token}'.")
            multiplier = 1
            if index + 1 < len(tokens) and tokens[index + 1].isdigit():
                index += 1
                multiplier = int(tokens[index])
            counts[-1][token] = counts[-1].get(token, 0) + multiplier
        index += 1
    if len(counts) != 1:
        raise ScienceError(f"'{formula}' has unbalanced brackets.")
    if not counts[0]:
        raise ScienceError(f"'{formula}' does not contain any elements.")
    return counts[0]


def molar_mass(formula: str) -> float:
    return sum(ATOMIC_WEIGHTS[element] * count for element, count in parse_formula(formula).items())


def _molar_mass_answer(formula: str) -> str:
    counts = parse_formula(formula)
    parts = [
        f"{element} {count} × {ATOMIC_WEIGHTS[element]}" for element, count in counts.items()
    ]
    total = sum(ATOMIC_WEIGHTS[element] * count for element, count in counts.items())
    return (
        f"Chemistry — molar mass of {formula}\n"
        f"Composition: {' + '.join(parts)}\n"
        f"Answer: {total:.3f} g/mol"
    )


def solve_chemistry(text: str) -> Optional[str]:
    """Answer molar mass, mole, pH and ideal gas questions."""

    lowered = text.lower()

    moles = re.search(
        rf"(?:how many moles|moles)\b[^\d]*(?P<mass>{NUMBER})\s*(?P<unit>kg|g|grams?)\b"
        rf"[^A-Za-z0-9]*(?:of\s+)?(?P<formula>[A-Za-z0-9()]+)",
        text,
        re.IGNORECASE,
    )
    if moles:
        try:
            mass_per_mole = molar_mass(moles.group("formula"))
        except ScienceError as exc:
            return str(exc)
        grams = float(moles.group("mass"))
        if moles.group("unit").lower() == "kg":
            grams *= 1000
        if mass_per_mole == 0:
            return "That formula has no mass I can use."
        return (
            f"Chemistry — moles of {moles.group('formula')}\n"
            f"Molar mass: {mass_per_mole:.3f} g/mol\n"
            "Formula: n = m / M\n"
            f"Answer: {grams / mass_per_mole:.4g} mol"
        )

    mass_match = re.search(
        r"(?:molar mass|molecular mass|molecular weight|formula mass|relative molecular mass)"
        r"[^A-Za-z0-9]*(?:of\s+)?(?P<formula>[A-Za-z0-9()]+)",
        text,
        re.IGNORECASE,
    )
    if mass_match:
        try:
            return _molar_mass_answer(mass_match.group("formula"))
        except ScienceError as exc:
            return str(exc)

    ph_from_conc = re.search(
        rf"\bph\b[^\d]*(?:of|for|when|with)?[^\d]*(?P<value>{NUMBER})\s*(?:m\b|mol/l|molar)",
        lowered,
    )
    if ph_from_conc:
        concentration = float(ph_from_conc.group("value"))
        if concentration <= 0:
            return "Concentration must be greater than zero to take a pH."
        return (
            "Chemistry — pH\n"
            f"Given: [H+] = {_fmt(concentration)} mol/L\n"
            "Formula: pH = -log10([H+])\n"
            f"Answer: pH = {-math.log10(concentration):.2f}"
        )

    conc_from_ph = re.search(
        rf"(?:concentration|\[h\+\]|hydrogen ion).*?\bph\b[^\d]*(?P<value>{NUMBER})", lowered
    )
    if conc_from_ph:
        ph_value = float(conc_from_ph.group("value"))
        return (
            "Chemistry — hydrogen ion concentration\n"
            f"Given: pH = {_fmt(ph_value)}\n"
            "Formula: [H+] = 10^-pH\n"
            f"Answer: [H+] = {10 ** -ph_value:.3g} mol/L"
        )

    if re.search(r"ideal gas|pv\s*=\s*nrt", lowered):
        values = {}
        for key, pattern in (
            ("pressure", rf"(?:pressure|p)\s*(?:=|is|of)?\s*(?P<value>{NUMBER})\s*(?:atm)"),
            ("volume", rf"(?:volume|v)\s*(?:=|is|of)?\s*(?P<value>{NUMBER})\s*(?:l\b|liters?|litres?)"),
            ("moles", rf"(?P<value>{NUMBER})\s*(?:mol\b|moles?)"),
            ("temperature", rf"(?:temperature|t)\s*(?:=|is|of)?\s*(?P<value>{NUMBER})\s*(?:k\b|kelvin)"),
        ):
            found = re.search(pattern, lowered)
            if found:
                values[key] = float(found.group("value"))
        known = set(values)
        if len(known) == 3:
            if "pressure" not in known:
                result = values["moles"] * GAS_CONSTANT * values["temperature"] / values["volume"]
                answer, unit, target = result, "atm", "pressure"
            elif "volume" not in known:
                result = values["moles"] * GAS_CONSTANT * values["temperature"] / values["pressure"]
                answer, unit, target = result, "L", "volume"
            elif "moles" not in known:
                result = values["pressure"] * values["volume"] / (GAS_CONSTANT * values["temperature"])
                answer, unit, target = result, "mol", "amount"
            else:
                result = values["pressure"] * values["volume"] / (GAS_CONSTANT * values["moles"])
                answer, unit, target = result, "K", "temperature"
            given = ", ".join(f"{key} = {_fmt(value)}" for key, value in values.items())
            return (
                f"Chemistry — ideal gas law ({target})\n"
                f"Given: {given}\n"
                "Formula: PV = nRT with R = 0.082057 L·atm/(mol·K)\n"
                f"Answer: {target} = {answer:.4g} {unit}"
            )
        return (
            "For the ideal gas law I need three of pressure (atm), volume (L), "
            "moles and temperature (K)."
        )
    return None


# ---------------------------------------------------------------------------
# Biology
# ---------------------------------------------------------------------------

_DNA_COMPLEMENT = {"A": "T", "T": "A", "G": "C", "C": "G"}

_CODON_DATA = (
    "TTT:F TTC:F TTA:L TTG:L CTT:L CTC:L CTA:L CTG:L ATT:I ATC:I ATA:I ATG:M "
    "GTT:V GTC:V GTA:V GTG:V TCT:S TCC:S TCA:S TCG:S CCT:P CCC:P CCA:P CCG:P "
    "ACT:T ACC:T ACA:T ACG:T GCT:A GCC:A GCA:A GCG:A TAT:Y TAC:Y TAA:* TAG:* "
    "CAT:H CAC:H CAA:Q CAG:Q AAT:N AAC:N AAA:K AAG:K GAT:D GAC:D GAA:E GAG:E "
    "TGT:C TGC:C TGA:* TGG:W CGT:R CGC:R CGA:R CGG:R AGT:S AGC:S AGA:R AGG:R "
    "GGT:G GGC:G GGA:G GGG:G"
)

CODON_TABLE: Dict[str, str] = {
    codon: amino
    for codon, amino in (entry.split(":") for entry in _CODON_DATA.split())
}


def _normalise_sequence(sequence: str) -> str:
    return re.sub(r"[^A-Za-z]", "", sequence).upper()


def _punnett(first: str, second: str) -> Optional[str]:
    if len(first) != 2 or len(second) != 2:
        return None
    if first[0].lower() != first[1].lower() or second[0].lower() != second[1].lower():
        return None
    if first[0].lower() != second[0].lower():
        return None
    offspring: Dict[str, int] = {}
    for left in first:
        for right in second:
            genotype = "".join(sorted((left, right), key=lambda char: (char.islower(), char)))
            offspring[genotype] = offspring.get(genotype, 0) + 1
    dominant = first[0].upper()
    dominant_count = sum(
        count for genotype, count in offspring.items() if dominant in genotype
    )
    genotypes = ", ".join(
        f"{genotype} {count}/4" for genotype, count in sorted(offspring.items())
    )
    return (
        f"Biology — monohybrid cross {first} × {second}\n"
        f"Genotypes: {genotypes}\n"
        f"Phenotypes: {dominant_count}/4 dominant, {4 - dominant_count}/4 recessive"
    )


def solve_biology(text: str) -> Optional[str]:
    """Answer DNA/RNA sequence questions and simple genetics crosses."""

    cross = re.search(r"\b(?P<first>[A-Za-z]{2})\s*(?:x|×|cross(?:ed)? with)\s*(?P<second>[A-Za-z]{2})\b", text)
    if cross and re.search(r"cross|punnett|offspring|genotype|phenotype", text, re.IGNORECASE):
        answer = _punnett(cross.group("first"), cross.group("second"))
        if answer:
            return answer

    sequence_match = re.search(
        r"\b(?P<sequence>[ACGTUacgtu]{3,})\b(?![A-Za-z])", text
    )
    lowered = text.lower()
    wants_sequence = re.search(
        r"complement|transcrib|translat|gc content|mrna|protein|rna sequence|dna sequence",
        lowered,
    )
    if not (sequence_match and wants_sequence):
        return None

    sequence = _normalise_sequence(sequence_match.group("sequence"))
    if "T" in sequence and "U" in sequence:
        return "That sequence mixes T and U, so I cannot tell if it is DNA or RNA."

    if "gc content" in lowered:
        gc = sum(1 for base in sequence if base in "GC")
        return (
            f"Biology — GC content of {sequence}\n"
            f"G + C bases: {gc} of {len(sequence)}\n"
            f"Answer: {gc / len(sequence) * 100:.1f}%"
        )

    if re.search(r"translat|protein|amino acid", lowered):
        coding = sequence.replace("U", "T")
        if len(coding) < 3:
            return "I need at least three bases to translate a codon."
        peptide = []
        for start in range(0, len(coding) - 2, 3):
            peptide.append(CODON_TABLE.get(coding[start : start + 3], "?"))
        leftover = len(coding) % 3
        lines = [
            f"Biology — translation of {sequence}",
            f"Codons: {' '.join(coding[i:i+3] for i in range(0, len(coding) - 2, 3))}",
            f"Answer: {''.join(peptide)} (* marks a stop codon)",
        ]
        if leftover:
            lines.append(f"Note: {leftover} leftover base(s) were ignored.")
        return "\n".join(lines)

    if re.search(r"transcrib|mrna|rna", lowered):
        if "U" in sequence:
            dna = sequence.replace("U", "T")
            return (
                f"Biology — reverse transcription of RNA {sequence}\n"
                f"Answer (DNA template read as coding strand): {dna}"
            )
        return (
            f"Biology — transcription of {sequence}\n"
            "Rule: the mRNA copies the coding strand with U in place of T.\n"
            f"Answer: {sequence.replace('T', 'U')}"
        )

    if "complement" in lowered:
        if "U" in sequence:
            return "Complementing works on DNA; give me a sequence of A, C, G and T."
        complement = "".join(_DNA_COMPLEMENT[base] for base in sequence)
        if re.search(r"reverse complement", lowered):
            return (
                f"Biology — reverse complement of {sequence}\n"
                f"Complement: {complement}\n"
                f"Answer: {complement[::-1]}"
            )
        return (
            f"Biology — complement of {sequence}\n"
            "Rule: A pairs with T, and C pairs with G.\n"
            f"Answer: {complement}"
        )
    return None


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

SOLVERS: Sequence[Callable[[str], Optional[str]]] = (
    solve_biology,
    solve_chemistry,
    solve_physics,
    solve_equation,
)


def solve_problem(text: str) -> Optional[str]:
    """Return a worked answer for a science question, or ``None``."""

    for solver in SOLVERS:
        try:
            answer = solver(text)
        except ScienceError as exc:
            return str(exc)
        if answer:
            return answer
    return None
