"""Example package functionality for the template project."""

from __future__ import annotations

import logging

LOGGER = logging.getLogger(__name__)


def do_useful_thing(name: str = "world") -> str:
    """Do the package's main useful thing."""
    LOGGER.info("Doing a useful thing for %s", name)
    return f"hello, {name}"
