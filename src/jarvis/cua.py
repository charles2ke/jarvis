"""Computer use agent (CUA) support.

Jarvis turns a plain English instruction such as ``open Safari then click on
the Save button and type hello`` into an ordered :class:`Plan` of
:class:`Action` steps. Planning is always offline and has no side effects.

Executing a plan drives the real machine, so it is opt-in: a backend command
must be configured with ``JARVIS_CUA_COMMAND`` and execution must be enabled
with ``JARVIS_CUA_ENABLED``. Without both, Jarvis reports the plan it would run
instead of touching the computer. Only the standard library is used, so Jarvis
stays dependency free.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

DEFAULT_TIMEOUT = 30.0

ENABLE_ENV_VAR = "JARVIS_CUA_ENABLED"
COMMAND_ENV_VAR = "JARVIS_CUA_COMMAND"

_TRUTHY = {"1", "true", "yes", "on", "enable", "enabled"}

#: The action kinds Jarvis can plan, with a short description of each.
ACTIONS: Tuple[Tuple[str, str], ...] = (
    ("open", "open an application, file or URL — 'open Safari', 'go to example.com'"),
    ("click", "click something on screen — 'click on the Save button'"),
    ("double_click", "double click something — 'double click the report'"),
    ("right_click", "open a context menu — 'right click the desktop'"),
    ("move", "move the pointer — 'move the mouse to the menu bar'"),
    ("drag", "drag one thing onto another — 'drag report.pdf to the bin'"),
    ("type", "type text — 'type hello Charles'"),
    ("key", "press a key or chord — 'press enter', 'press ctrl+s'"),
    ("scroll", "scroll the screen — 'scroll down 3'"),
    ("wait", "pause — 'wait 2 seconds'"),
    ("screenshot", "capture the screen — 'take a screenshot'"),
)

_ACTION_NAMES: Tuple[str, ...] = tuple(name for name, _ in ACTIONS)

_STEP_SPLIT = re.compile(
    r"\s*(?:,\s*(?:and\s+)?(?:then\s+)?|;\s*|\.\s+|\s+and\s+then\s+|\s+then\s+|\s+and\s+)",
    re.IGNORECASE,
)

_LEADING_NOISE = re.compile(
    r"^(?:please\s+|could you\s+|can you\s+|now\s+|next\s+|after that\s+|finally\s+)+",
    re.IGNORECASE,
)

_ARTICLE = re.compile(r"^(?:the|a|an|on|onto|at|to)\s+", re.IGNORECASE)


class CuaError(RuntimeError):
    """Raised when an instruction cannot be planned or a plan cannot run."""


@dataclass(frozen=True)
class Action:
    """A single computer use step."""

    kind: str
    target: str = ""
    value: str = ""

    def describe(self) -> str:
        if self.kind == "open":
            return f"open {self.target}"
        if self.kind == "click":
            return f"click {self.target}"
        if self.kind == "double_click":
            return f"double click {self.target}"
        if self.kind == "right_click":
            return f"right click {self.target}"
        if self.kind == "move":
            return f"move the pointer to {self.target}"
        if self.kind == "drag":
            return f"drag {self.target} to {self.value}"
        if self.kind == "type":
            return f"type {self.value!r}"
        if self.kind == "key":
            return f"press {self.value}"
        if self.kind == "scroll":
            return f"scroll {self.target} {self.value}"
        if self.kind == "wait":
            unit = "second" if self.value == "1" else "seconds"
            return f"wait {self.value} {unit}"
        if self.kind == "screenshot":
            return "take a screenshot"
        return self.kind  # pragma: no cover - defensive

    def arguments(self) -> Tuple[str, ...]:
        """Return the backend command arguments for this action."""

        parts = [self.kind]
        if self.target:
            parts.append(self.target)
        if self.value:
            parts.append(self.value)
        return tuple(parts)


@dataclass(frozen=True)
class Plan:
    """An ordered list of actions parsed from one instruction."""

    instruction: str
    actions: Sequence[Action] = field(default_factory=tuple)

    def summary(self) -> str:
        lines = [f"Computer use plan for: {self.instruction}"]
        lines.extend(
            f"{index}. {action.describe()}"
            for index, action in enumerate(self.actions, start=1)
        )
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self.actions)

    def __iter__(self):
        return iter(self.actions)


def _clean(text: str) -> str:
    return _ARTICLE.sub("", text.strip()).strip().strip('"').strip("'").strip()


def _quoted_or_rest(text: str) -> str:
    found = re.match(r"^[\"'](?P<value>.*)[\"']\s*$", text.strip())
    if found is not None:
        return found.group("value")
    return text.strip().rstrip(".!?")


def _parse_step(step: str) -> Action:
    text = _LEADING_NOISE.sub("", step.strip()).strip()
    text = text.rstrip(".!")
    if not text:
        raise CuaError("empty step")
    lowered = text.lower()

    if re.match(r"^(?:take |grab |capture )?(?:a )?screen ?(?:shot|grab)$", lowered):
        return Action("screenshot")

    found = re.match(
        r"^(?:wait|pause|sleep)(?:\s+for)?(?:\s+(?P<seconds>\d+)(?:\s+seconds?)?)?$",
        lowered,
    )
    if found is not None:
        return Action("wait", value=found.group("seconds") or "1")

    found = re.match(
        r"^scroll\s+(?P<direction>up|down|left|right)(?:\s+(?:by\s+)?(?P<amount>\d+))?$",
        lowered,
    )
    if found is not None:
        return Action("scroll", target=found.group("direction"), value=found.group("amount") or "3")

    found = re.match(r"^(?:press|hit|tap)\s+(?:the\s+)?(?P<key>.+?)(?:\s+key)?$", text, re.IGNORECASE)
    if found is not None:
        return Action("key", value=_clean(found.group("key")).lower())

    found = re.match(
        r"^(?:type|enter|write|input)\s+(?P<text>.+?)"
        r"(?:\s+(?:in|into|on)\s+(?:the\s+)?(?P<target>.+))?$",
        text,
        re.IGNORECASE,
    )
    if found is not None:
        value = _quoted_or_rest(found.group("text"))
        if not value:
            raise CuaError("I need to know what to type")
        return Action("type", target=_clean(found.group("target") or ""), value=value)

    found = re.match(r"^drag\s+(?P<source>.+?)\s+(?:to|onto|into)\s+(?P<target>.+)$", text, re.IGNORECASE)
    if found is not None:
        return Action("drag", target=_clean(found.group("source")), value=_clean(found.group("target")))

    found = re.match(
        r"^(?:move|point)\s+(?:the\s+)?(?:mouse|pointer|cursor)?\s*(?:to|onto|over)\s+(?P<target>.+)$",
        text,
        re.IGNORECASE,
    )
    if found is not None:
        return Action("move", target=_clean(found.group("target")))

    found = re.match(
        r"^(?P<modifier>double|right|left)[- ]?click(?:\s+(?:on|at))?\s+(?P<target>.+)$",
        text,
        re.IGNORECASE,
    )
    if found is not None:
        modifier = found.group("modifier").lower()
        kind = {"double": "double_click", "right": "right_click", "left": "click"}[modifier]
        return Action(kind, target=_clean(found.group("target")))

    found = re.match(r"^(?:click|select|choose|press on)(?:\s+(?:on|at))?\s+(?P<target>.+)$", text, re.IGNORECASE)
    if found is not None:
        return Action("click", target=_clean(found.group("target")))

    found = re.match(
        r"^(?:open|launch|start|run|go to|visit|navigate to|switch to)\s+(?P<target>.+)$",
        text,
        re.IGNORECASE,
    )
    if found is not None:
        target = _clean(found.group("target"))
        if not target:
            raise CuaError("I need to know what to open")
        return Action("open", target=target)

    raise CuaError(f"I do not know how to do '{text}' on the computer")


_QUOTED_SPAN = re.compile(r'"[^"]*"|\'[^\']*\'')


def _normalize_whitespace_outside_quotes(text: str) -> str:
    """Collapse runs of whitespace, but leave quoted spans untouched."""

    pieces = re.split(r'("[^"]*"|\'[^\']*\')', text)
    return "".join(
        piece if index % 2 else re.sub(r"\s+", " ", piece)
        for index, piece in enumerate(pieces)
    ).strip()


def _split_steps(text: str) -> List[str]:
    """Split ``text`` on step separators that are not inside quotes."""

    quoted_spans = [match.span() for match in _QUOTED_SPAN.finditer(text)]
    steps: List[str] = []
    last = 0
    for match in _STEP_SPLIT.finditer(text):
        if any(start <= match.start() < end for start, end in quoted_spans):
            continue
        steps.append(text[last:match.start()])
        last = match.end()
    steps.append(text[last:])
    return steps


def plan(instruction: str) -> Plan:
    """Parse ``instruction`` into a :class:`Plan`."""

    text = _normalize_whitespace_outside_quotes(instruction or "")
    if not text:
        raise CuaError("Tell me what you would like me to do on the computer.")
    steps = [step for step in _split_steps(text) if step and step.strip()]
    actions: List[Action] = []
    for step in steps:
        try:
            actions.append(_parse_step(step))
        except CuaError as exc:
            if actions:
                raise CuaError(
                    f"{exc} (I understood the first {len(actions)} step(s))."
                ) from exc
            raise
    if not actions:  # pragma: no cover - defensive
        raise CuaError("Tell me what you would like me to do on the computer.")
    return Plan(instruction=text, actions=tuple(actions))


def is_enabled(environ: Optional[Dict[str, str]] = None) -> bool:
    """Return ``True`` when computer use execution has been opted into."""

    env = os.environ if environ is None else environ
    return str(env.get(ENABLE_ENV_VAR, "")).strip().lower() in _TRUTHY


def backend_command(environ: Optional[Dict[str, str]] = None) -> List[str]:
    """Return the configured backend command, or raise :class:`CuaError`."""

    env = os.environ if environ is None else environ
    configured = (env.get(COMMAND_ENV_VAR) or "").strip()
    if not configured:
        raise CuaError(
            "No computer use backend is configured. "
            f"Set {COMMAND_ENV_VAR} to a command that performs one action, "
            "for example 'my-cua-tool'."
        )
    try:
        parts = shlex.split(configured)
    except ValueError as exc:
        raise CuaError(f"I could not read {COMMAND_ENV_VAR}: {exc}") from exc
    if not parts:
        raise CuaError(f"{COMMAND_ENV_VAR} is empty.")
    return parts


def run_action(action: Action, *, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Run one ``action`` through the configured backend command."""

    command = [*backend_command(), *action.arguments()]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    except FileNotFoundError as exc:
        raise CuaError(f"I could not run the computer use backend: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CuaError(f"The computer use backend timed out on '{action.describe()}'.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        message = f"The computer use backend failed on '{action.describe()}'"
        raise CuaError(f"{message}: {detail}" if detail else f"{message}.") from exc
    except OSError as exc:
        raise CuaError(f"I could not run the computer use backend: {exc}") from exc
    return (result.stdout or "").strip()


def execute(
    instruction: str,
    *,
    runner: Optional[Callable[[Action], str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Plan ``instruction`` and, when enabled, run it on this computer."""

    parsed = plan(instruction)
    if not is_enabled():
        return (
            f"{parsed.summary()}\n"
            f"I did not run it: set {ENABLE_ENV_VAR}=1 (and {COMMAND_ENV_VAR}) "
            "to let me use the computer."
        )
    step = runner or (lambda action: run_action(action, timeout=timeout))
    lines = [f"Computer use run for: {parsed.instruction}"]
    for index, action in enumerate(parsed.actions, start=1):
        output = (step(action) or "").strip()
        line = f"{index}. {action.describe()}"
        lines.append(f"{line} — {output}" if output else f"{line} — done")
    return "\n".join(lines)


def actions_chart() -> str:
    """Return a human readable list of the supported actions."""

    lines = [f"I can plan {len(ACTIONS)} computer use actions:"]
    lines.extend(f"- {name}: {description}" for name, description in ACTIONS)
    lines.append("Try 'use the computer to open Safari then click on Sign in'.")
    return "\n".join(lines)
