"""Tests for qstatus import and CLI behavior."""

from __future__ import annotations

import qstatus
from qstatus.cli import main


def test_package_exposes_version() -> None:
    """Verify the package exposes its version."""
    assert qstatus.__version__ == "0.1.0"


def test_cli_prints_version(capsys) -> None:
    """Verify the starter CLI can run after installation."""
    assert main([]) == 0
    assert capsys.readouterr().out.strip() == "qstatus 0.1.0"
