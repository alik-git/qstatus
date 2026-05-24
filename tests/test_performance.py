"""Performance regression tests for qstatus fast paths."""

from __future__ import annotations

import stat
import time
from typing import TYPE_CHECKING

from qstatus.cli import main
from qstatus.env_render import render_env_human
from qstatus.env_snapshot import collect_env_snapshot

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


ENV_COLLECT_BUDGET_S = 0.08
ENV_RENDER_BUDGET_S = 0.03
ENV_MAIN_BUDGET_S = 0.12


def test_env_default_fast_path_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Default env output should stay fast and avoid optional version probes."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname = "demo"\n')

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("python", "python3", "uv", "conda", "devpy", "pip", "pip3"):
        _slow_version_executable(bin_dir / name)
    env = {"PATH": str(bin_dir), "HOME": str(tmp_path)}

    collect_start = time.perf_counter()
    snapshot = collect_env_snapshot(project, env=env)
    collect_s = time.perf_counter() - collect_start

    render_start = time.perf_counter()
    render_env_human(snapshot, color=False)
    render_s = time.perf_counter() - render_start

    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("HOME", str(tmp_path))
    main_start = time.perf_counter()
    assert main(["env", "--cwd", str(project), "--plain"]) == 0
    main_s = time.perf_counter() - main_start
    capsys.readouterr()

    breakdown = (
        f"collect={collect_s:.4f}s render={render_s:.4f}s main={main_s:.4f}s; "
        "default qstatus env should use path probes only. "
        "If this fails, check for accidental version subprocesses or broad scans."
    )
    assert collect_s < ENV_COLLECT_BUDGET_S, breakdown
    assert render_s < ENV_RENDER_BUDGET_S, breakdown
    assert main_s < ENV_MAIN_BUDGET_S, breakdown


def _slow_version_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\nsleep 0.1\necho slow-version\n")
    path.chmod(stat.S_IRWXU)
