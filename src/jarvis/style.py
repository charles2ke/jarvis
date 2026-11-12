"""Terminal styling for the Jarvis command line.

Colour is purely presentational: it is added when text is printed, never to
the replies that skills return, and it switches itself off whenever it could
get in the way, following https://no-color.org:

* ``--color never`` or a non-empty ``NO_COLOR`` turns it off;
* ``--color always`` or a non-empty ``FORCE_COLOR`` (other than ``0``) turns
  it on, even when output is piped;
* otherwise it is used only when the output is an interactive terminal whose
  ``TERM`` is not ``dumb``.

When colour is off every helper returns its input unchanged, so piped output
stays plain text.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Mapping, Optional, TextIO

COLOR_MODES = ("auto", "always", "never")

_SGR = {
    "bold": "1",
    "dim": "2",
    "italic": "3",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
}
_RESET = "\033[0m"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_SKILL_LINE = re.compile(r"^(- )([\w-]+)(:.*)$")
_EXAMPLE_LINE = re.compile(r"^(\s+)(e\.g\.\s.*)$")
_QUOTED = re.compile(r"'([^'\n]+)'")


def strip_ansi(text: str) -> str:
    """Remove colour escape sequences from ``text``."""

    return _ANSI.sub("", text)


def color_enabled(
    stream: Optional[TextIO] = None,
    mode: str = "auto",
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    """Decide whether output written to ``stream`` should be coloured."""

    if mode not in COLOR_MODES:
        raise ValueError(f"unknown colour mode {mode!r}; use one of {', '.join(COLOR_MODES)}")
    if mode != "auto":
        return mode == "always"
    env = os.environ if environ is None else environ
    if env.get("NO_COLOR"):
        return False
    if env.get("FORCE_COLOR", "") not in ("", "0"):
        return True
    if env.get("TERM") == "dumb":
        return False
    target = sys.stdout if stream is None else stream
    try:
        return bool(target.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def _enable_virtual_terminal(stream: TextIO) -> bool:
    """Ask a Windows console to interpret ANSI escapes; always true elsewhere."""

    if os.name != "nt":
        return True
    try:  # pragma: no cover - only reachable on Windows
        import ctypes
        import msvcrt

        handle = msvcrt.get_osfhandle(stream.fileno())
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        console_mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(console_mode)):
            return False
        enable_virtual_terminal_processing = 0x0004
        return bool(
            kernel32.SetConsoleMode(handle, console_mode.value | enable_virtual_terminal_processing)
        )
    except Exception:  # pragma: no cover - only reachable on Windows
        return False


def _can_encode(stream: Optional[TextIO], text: str) -> bool:
    encoding = getattr(stream, "encoding", None) or "ascii"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


class Style:
    """Paints the command line chrome: prompts, prefixes and headings."""

    def __init__(self, enabled: bool = False, *, unicode: bool = True) -> None:
        self.enabled = enabled
        self.unicode = unicode

    @classmethod
    def for_stream(
        cls,
        stream: Optional[TextIO] = None,
        mode: str = "auto",
        environ: Optional[Mapping[str, str]] = None,
    ) -> "Style":
        """Build the style that suits ``stream`` and the user's preferences."""

        target = sys.stdout if stream is None else stream
        enabled = color_enabled(target, mode, environ)
        if enabled and not _enable_virtual_terminal(target) and mode == "auto":
            enabled = False
        return cls(enabled, unicode=_can_encode(target, "\u25c6\u00b7"))

    def paint(self, text: str, *styles: str) -> str:
        """Wrap ``text`` in the given SGR styles when colour is on."""

        if not self.enabled or not text or not styles:
            return text
        codes = ";".join(_SGR[name] for name in styles)
        return f"\033[{codes}m{text}{_RESET}"

    def banner(self, version: str) -> str:
        """A one line title shown above the greeting, only when colour is on."""

        if not self.enabled:
            return ""
        mark, dot = ("\u25c6", "\u00b7") if self.unicode else ("*", "-")
        title = self.paint(f"{mark} Jarvis", "bold", "cyan")
        detail = self.paint(f"v{version} {dot} your personal AI companion", "dim")
        return f"{title} {detail}"

    def greeting(self, text: str) -> str:
        """Highlight the quoted commands (``'help'``, ``'exit'``) in ``text``."""

        if not self.enabled:
            return text
        return _QUOTED.sub(lambda m: f"'{self.paint(m.group(1), 'bold', 'yellow')}'", text)

    def prompt(self) -> str:
        """The ``you>`` prompt handed to :func:`input`."""

        if not self.enabled:
            return "you> "
        # readline counts every character of the prompt unless escapes are
        # wrapped in \001 and \002, which would break cursor positioning.
        start, end = ("\001", "\002") if "readline" in sys.modules else ("", "")
        return f"{start}\033[{_SGR['bold']};{_SGR['green']}m{end}you>{start}{_RESET}{end} "

    def reply(self, text: str) -> str:
        """Prefix a reply with ``jarvis>`` for an interactive session."""

        return f"{self.paint('jarvis>', 'bold', 'cyan')} {self.highlight(text)}"

    def highlight(self, text: str) -> str:
        """Emphasise skill names and dim examples in skill lists."""

        if not self.enabled:
            return text
        lines = []
        for line in text.split("\n"):
            skill = _SKILL_LINE.match(line)
            example = None if skill else _EXAMPLE_LINE.match(line)
            if skill:
                line = skill.group(1) + self.paint(skill.group(2), "bold", "magenta") + skill.group(3)
            elif example:
                line = example.group(1) + self.paint(example.group(2), "dim")
            lines.append(line)
        return "\n".join(lines)

    def skill_entry(self, name: str, description: str, example: Optional[str]) -> str:
        """One ``--list-skills`` entry."""

        lines = [f"{self.paint(name, 'bold', 'magenta')}: {description}"]
        if example:
            lines.append(self.paint(f"    e.g. {example}", "dim"))
        return "\n".join(lines)

    def note(self, text: str) -> str:
        """De-emphasise an aside such as a hint or a warning."""

        return self.paint(text, "dim")
