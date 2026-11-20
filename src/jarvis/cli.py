"""Command line interface for Jarvis."""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Sequence

from jarvis import __version__, websearch
from jarvis.assistant import Assistant
from jarvis.memory import DEFAULT_MEMORY_PATH, Memory
from jarvis.skills import build_default_registry
from jarvis.speech import SpeechError, speak
from jarvis.style import COLOR_MODES, Style

EXIT_COMMANDS = {"exit", "quit", ":q"}
WEB_SEARCH_ENV = "JARVIS_WEB_SEARCH"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="Jarvis, your personal AI companion.",
        epilog=(
            "Examples:\n"
            "  jarvis                      start an interactive session\n"
            '  jarvis "calculate 21 * 2"   ask one question and exit\n'
            '  echo "what is the time?" | jarvis\n'
            '  jarvis "who invented the telephone?"\n'
            "                              look up what Jarvis does not know online\n"
            "  jarvis --web-search off     stay offline (or JARVIS_WEB_SEARCH=off)\n"
            "  jarvis --list-skills\n"
            "  NO_COLOR=1 jarvis           plain output (or --color never)\n"
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
    parser.add_argument(
        "--color",
        "--colour",
        choices=COLOR_MODES,
        default="auto",
        help=(
            "Colour prompts and headings: 'auto' (default) only on an interactive "
            "terminal and never when NO_COLOR is set, 'always', or 'never'."
        ),
    )
    parser.add_argument(
        "--web-search",
        choices=websearch.MODES,
        default=None,
        help=(
            "When to search the web: 'auto' (default) also looks up questions no "
            "skill can answer, 'manual' only when you ask ('search the web for "
            f"...'), 'off' never. Defaults to ${WEB_SEARCH_ENV} when that is set."
        ),
    )
    parser.add_argument("--version", action="version", version=f"jarvis {__version__}")
    return parser


def _web_search_mode(args: argparse.Namespace, parser: argparse.ArgumentParser) -> str:
    if args.web_search:
        return args.web_search
    value = os.environ.get(WEB_SEARCH_ENV, "").strip().lower()
    if not value:
        return "auto"
    if value not in websearch.MODES:
        parser.error(
            f"{WEB_SEARCH_ENV} must be one of {', '.join(websearch.MODES)}, not '{value}'"
        )
    return value


def _say_aloud(reply: str, style: Style) -> None:
    try:
        speak(reply)
    except SpeechError as exc:
        print(style.note(f"(speech unavailable: {exc})"))


def _list_skills(style: Style) -> int:
    for skill in build_default_registry():
        example = skill.examples[0] if skill.examples else None
        print(style.skill_entry(skill.name, skill.description, example))
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
    parser = build_parser()
    args = parser.parse_args(argv)
    web_search = _web_search_mode(args, parser)
    style = Style.for_stream(sys.stdout, args.color)
    if args.list_skills:
        return _list_skills(style)

    notes = Style.for_stream(sys.stderr, args.color)

    def notify(text: str) -> None:
        # Progress goes to stderr so piped replies stay clean.
        print(notes.note(text), file=sys.stderr, flush=True)

    memory = Memory(None if args.no_memory else args.memory)
    assistant = Assistant(memory=memory, web_search=web_search, notify=notify)

    piped = [] if args.message else _piped_lines()
    message = " ".join(args.message) if args.message else ""
    if len(piped) == 1:
        message = piped.pop()
    if message:
        reply = assistant.respond(message)
        print(style.highlight(reply))
        if args.speak:
            _say_aloud(reply, style)
        return 0

    banner = style.banner(__version__)
    if banner:
        print(banner)
    print(style.greeting(assistant.greet()))
    while True:
        try:
            message = piped.pop(0) if piped else input(style.prompt())
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print("\n" + style.note("(press Ctrl-D or type 'exit' to leave)"))
            continue
        if message.strip().lower() in EXIT_COMMANDS:
            break
        try:
            reply = assistant.respond(message)
        except KeyboardInterrupt:
            print("\n" + style.note("(cancelled)"))
            continue
        print(style.reply(reply))
        if args.speak:
            _say_aloud(reply, style)
    print(style.reply("Goodbye."))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
