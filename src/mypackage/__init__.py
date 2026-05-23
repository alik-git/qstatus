"""Example package used by the Python package template."""

from __future__ import annotations

import logging

from mypackage.package import do_useful_thing

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = ["do_useful_thing"]
