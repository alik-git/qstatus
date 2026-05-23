"""Command-line entry point for qstatus."""

from __future__ import annotations

import argparse
import sys

from qstatus import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the qstatus command-line parser."""
    parser = argparse.ArgumentParser(
        prog="qstatus",
        description="Print a quick local workspace status.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="print the installed qstatus version and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the qstatus command-line interface."""
    build_parser().parse_args(argv)
    print(f"qstatus {__version__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
