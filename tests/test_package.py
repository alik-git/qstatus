"""Tests for package import and metadata behavior."""

from __future__ import annotations

import mypackage


def test_do_useful_thing() -> None:
    """Verify the package's public starter function."""
    assert mypackage.do_useful_thing("template") == "hello, template"
