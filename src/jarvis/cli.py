"""Command line interface for Jarvis."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional, Sequence

from jarvis import __version__
from jarvis.assistant import Assistant
from jarvis.memory import DEFAULT_MEMORY_PATH, Memory
from jarvis.skills import build_default_registry
from jarvis.speech import SpeechError, speak

EXIT_COMMANDS = {"exit", "quit", ":q"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="Jarvis, your personal AI companion.",
        epilog=(
            "Examples:\n"
            "  jarvis                      start an interactive session\n"
            '  jarvis "calculate 21 * 2"   ask one question and exit\n'
            '  echo "what is the time?" | jarvis\n'
            "  jarvis --list-skills\n"
            "\nInside a session, type 'help' for the skill list, 'help <topic>' to\n"
            "filter it, and 'exit' (or Ctrl-D) to leave."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "message",
        nargs="*",
        help=(
            "Message to send to Jarvis. Omit it to start an interactive session, "
            "or pipe the message in on standard input."
        ),
    )
    parser.add_argument(
        "--memory",
        default=str(DEFAULT_MEMORY_PATH),
        help=f"Path to the memory file (default: {DEFAULT_MEMORY_PATH}).",
    )
    parser.add_argument(
        "--no-memory",
        action="store_true",
        help="Run without persisting anything to disk.",
    )
    parser.add_argument(
        "--speak",
        action="store_true",
        help="Also read every reply aloud with the system text to speech voice.",
    )
    parser.add_argument(
        "--list-skills",
        action="store_true",
        help="Print every skill with an example and exit.",
    )
    parser.add_argument("--version", action="version", version=f"jarvis {__version__}")
    return parser


def _say_aloud(reply: str) -> None:
    try:
        speak(reply)
    except SpeechError as exc:
        print(f"(speech unavailable: {exc})")


def _list_skills() -> int:
    for skill in build_default_registry():
        print(f"{skill.name}: {skill.description}")
        if skill.examples:
            print(f"    e.g. {skill.examples[0]}")
    return 0


def _piped_lines() -> List[str]:
    """Return the lines piped in on standard input, if any."""

    if sys.stdin is None or sys.stdin.isatty():
        return []
    try:
        data = sys.stdin.read()
    except (OSError, ValueError):  # pragma: no cover - closed or unreadable stdin
        return []
    return [line.strip() for line in data.splitlines() if line.strip()]


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_skills:
        return _list_skills()

    memory = Memory(None if args.no_memory else args.memory)
    assistant = Assistant(memory=memory)

    piped = [] if args.message else _piped_lines()
    message = " ".join(args.message) if args.message else ""
    if len(piped) == 1:
        message = piped.pop()
    if message:
        reply = assistant.respond(message)
        print(reply)
        if args.speak:
            _say_aloud(reply)
        return 0

    print(assistant.greet())
    while True:
        try:
            message = piped.pop(0) if piped else input("you> ")
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print("\n(press Ctrl-D or type 'exit' to leave)")
            continue
        if message.strip().lower() in EXIT_COMMANDS:
            break
        reply = assistant.respond(message)
        print(f"jarvis> {reply}")
        if args.speak:
            _say_aloud(reply)
    print("jarvis> Goodbye.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
