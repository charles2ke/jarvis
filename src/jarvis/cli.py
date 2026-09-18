"""Command line interface for Jarvis."""

from __future__ import annotations

import argparse
from typing import Optional, Sequence

from jarvis import __version__
from jarvis.assistant import Assistant
from jarvis.memory import DEFAULT_MEMORY_PATH, Memory

EXIT_COMMANDS = {"exit", "quit", ":q"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis", description="Jarvis, your personal AI companion."
    )
    parser.add_argument(
        "message",
        nargs="*",
        help="Message to send to Jarvis. Omit it to start an interactive session.",
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
    parser.add_argument("--version", action="version", version=f"jarvis {__version__}")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    memory = Memory(None if args.no_memory else args.memory)
    assistant = Assistant(memory=memory)

    if args.message:
        print(assistant.respond(" ".join(args.message)))
        return 0

    print(assistant.greet())
    while True:
        try:
            message = input("you> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if message.strip().lower() in EXIT_COMMANDS:
            print("jarvis> Goodbye.")
            break
        print(f"jarvis> {assistant.respond(message)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
