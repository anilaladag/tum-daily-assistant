"""Command line entry point: python -m tum_daily_assistant <command>."""

import argparse
import sys

from . import __version__

COMMANDS = {
    "run": "Read the calendar and update the reminders",
    "discover": "List calendars and trigger the permission prompts",
    "preview": "Print the messages that would be created",
    "settings": "Open the local settings form",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tum_daily_assistant")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    for name, help_text in COMMANDS.items():
        sub.add_parser(name, help=help_text)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    print(f"{args.command}: not implemented")
    return 0


if __name__ == "__main__":
    sys.exit(main())
