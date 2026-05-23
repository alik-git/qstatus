"""Command-line entry point for the example package."""

from __future__ import annotations

import logging
import sys

import colorlog

from mypackage import do_useful_thing

LOGGER = logging.getLogger(__name__)


def _configure_logging(level: int = logging.INFO) -> None:
    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            "%(log_color)s%(levelname)-8s%(reset)s %(name)s - %(message)s",
        ),
    )

    logging.basicConfig(level=level, handlers=[handler], force=True)


def main() -> int:
    """Run the package command-line interface."""
    _configure_logging()
    LOGGER.info("Starting mypackage")
    LOGGER.info("Result: %s", do_useful_thing())
    return 0


if __name__ == "__main__":
    sys.exit(main())
