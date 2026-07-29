"""Bounded GitHub CLI execution with explicit optional response caching."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from quick_status.commands import CommandResult, run_command

if TYPE_CHECKING:
    from quick_status.models import CommandRecord

_CACHE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class JsonQueryResult:
    """One typed JSON query result and its command-level error, if any."""

    data: dict[str, Any] | list[dict[str, Any]] | None
    command: CommandResult
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Return true when the command and JSON decoding both succeeded."""
        return self.command.ok and self.data is not None


@dataclass(frozen=True, slots=True)
class GitHubProvenance:
    """Aggregate freshness facts for commands issued by a GitHub client."""

    source: str
    collected_at: str | None
    age_seconds: float | None


class GitHubMemoryCache:
    """Share exact successful responses within one batch invocation."""

    def __init__(self) -> None:
        """Initialize an empty thread-safe response memo."""
        self._entries: dict[str, tuple[CommandResult, float]] = {}
        self._key_locks: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()

    def get(self, key: str, *, cwd: Path) -> CommandResult | None:
        """Return one same-invocation live result when available."""
        with self._lock:
            entry = self._entries.get(key)
        if entry is None:
            return None
        result, collected_epoch = entry
        return replace(
            result,
            cwd=cwd,
            duration_ms=0.0,
            age_seconds=max(0.0, time.time() - collected_epoch),
        )

    def put(self, key: str, result: CommandResult) -> None:
        """Store one successful decoded result for this invocation."""
        with self._lock:
            self._entries[key] = (result, time.time())

    def lock_for(self, key: str) -> threading.Lock:
        """Return a stable lock that single-flights one exact query."""
        with self._lock:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._key_locks[key] = lock
            return lock


class GitHubClient:
    """Run `gh` queries within one deadline and an opt-in cache boundary."""

    def __init__(
        self,
        root: Path,
        *,
        include_commands: bool = False,
        max_age_s: float = 0.0,
        timeout_s: float = 10.0,
        cache_dir: Path | None = None,
        memory_cache: GitHubMemoryCache | None = None,
    ) -> None:
        """Initialize one bounded client for a repository collection."""
        self.root = root
        self.include_commands = include_commands
        self.max_age_s = max(0.0, max_age_s)
        self.deadline = time.monotonic() + max(0.1, timeout_s)
        self.cache_dir = cache_dir or default_cache_dir()
        self.memory_cache = memory_cache
        self.records: list[CommandRecord] = []
        self._results: list[CommandResult] = []
        self._lock = threading.Lock()

    def json_list(
        self,
        args: list[str],
        *,
        timeout_s: float = 8.0,
    ) -> JsonQueryResult:
        """Run a `gh` query expected to return a JSON list."""
        return self._json(args, expected="list", timeout_s=timeout_s)

    def json_object(
        self,
        args: list[str],
        *,
        timeout_s: float = 8.0,
    ) -> JsonQueryResult:
        """Run a `gh` query expected to return a JSON object."""
        return self._json(args, expected="object", timeout_s=timeout_s)

    def run(self, args: list[str], *, timeout_s: float = 8.0) -> CommandResult:
        """Run an uncached `gh` command within the remaining deadline."""
        result = self._run_live(args, timeout_s=timeout_s)
        self._record(result)
        return result

    def provenance(self) -> GitHubProvenance:
        """Summarize whether collected GitHub evidence was live or cached."""
        with self._lock:
            results = list(self._results)
        if not results:
            return GitHubProvenance(source="live", collected_at=None, age_seconds=None)
        sources = {result.source for result in results}
        source = next(iter(sources)) if len(sources) == 1 else "mixed"
        timestamps = [
            result.collected_at for result in results if result.collected_at is not None
        ]
        ages = [
            result.age_seconds for result in results if result.age_seconds is not None
        ]
        return GitHubProvenance(
            source=source,
            collected_at=min(timestamps) if timestamps else None,
            age_seconds=round(max(ages), 3) if ages else None,
        )

    def _json(
        self,
        args: list[str],
        *,
        expected: str,
        timeout_s: float,
    ) -> JsonQueryResult:
        key = self._cache_key(args)
        if self.memory_cache is not None:
            with self.memory_cache.lock_for(key):
                return self._json_locked(
                    args,
                    key=key,
                    expected=expected,
                    timeout_s=timeout_s,
                )
        return self._json_locked(
            args,
            key=key,
            expected=expected,
            timeout_s=timeout_s,
        )

    def _json_locked(
        self,
        args: list[str],
        *,
        key: str,
        expected: str,
        timeout_s: float,
    ) -> JsonQueryResult:
        memory = (
            self.memory_cache.get(key, cwd=self.root)
            if self.memory_cache is not None
            else None
        )
        if memory is not None:
            data = _decode(memory.stdout, expected=expected)
            if data is not None:
                self._record(memory)
                return JsonQueryResult(data=data, command=memory)
        cached = self._load(args)
        if cached is not None:
            data = _decode(cached.stdout, expected=expected)
            if data is not None:
                self._record(cached)
                return JsonQueryResult(data=data, command=cached)

        result = self._run_live(args, timeout_s=timeout_s)
        data = _decode(result.stdout, expected=expected) if result.ok else None
        error = None
        if not result.ok:
            error = bounded_error(result)
        elif data is None:
            error = "invalid JSON response"
        else:
            if self.memory_cache is not None:
                self.memory_cache.put(key, result)
            self._save(args, result)
        self._record(result)
        return JsonQueryResult(data=data, command=result, error=error)

    def _run_live(self, args: list[str], *, timeout_s: float) -> CommandResult:
        remaining = self.deadline - time.monotonic()
        command = ("gh", *(str(arg) for arg in args))
        collected_at = _now_iso()
        if remaining <= 0:
            return CommandResult(
                args=command,
                cwd=self.root,
                exit_code=None,
                stdout="",
                stderr="GitHub collection deadline exceeded",
                timed_out=True,
                collected_at=collected_at,
                age_seconds=0.0,
            )
        result = run_command(
            list(command),
            cwd=self.root,
            timeout_s=min(timeout_s, remaining),
        )
        return replace(result, collected_at=collected_at, age_seconds=0.0)

    def _record(self, result: CommandResult) -> None:
        with self._lock:
            self._results.append(result)
            if self.include_commands:
                self.records.append(result.evidence())

    def _load(self, args: list[str]) -> CommandResult | None:
        if self.max_age_s <= 0:
            return None
        path = self._cache_path(args)
        try:
            payload = json.loads(path.read_text())
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("schema_version") != _CACHE_SCHEMA_VERSION:
            return None
        collected_epoch = payload.get("collected_epoch")
        stdout = payload.get("stdout")
        collected_at = payload.get("collected_at")
        if not isinstance(collected_epoch, int | float) or not isinstance(stdout, str):
            return None
        if not isinstance(collected_at, str):
            return None
        age = max(0.0, time.time() - float(collected_epoch))
        if age > self.max_age_s:
            return None
        return CommandResult(
            args=("gh", *(str(arg) for arg in args)),
            cwd=self.root,
            exit_code=0,
            stdout=stdout,
            stderr="",
            source="cache",
            collected_at=collected_at,
            age_seconds=age,
        )

    def _save(self, args: list[str], result: CommandResult) -> None:
        if self.max_age_s <= 0 or not result.ok:
            return
        path = self._cache_path(args)
        payload = {
            "schema_version": _CACHE_SCHEMA_VERSION,
            "collected_at": result.collected_at or _now_iso(),
            "collected_epoch": time.time(),
            "stdout": result.stdout,
        }
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            temporary = path.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_text(json.dumps(payload, separators=(",", ":")))
            temporary.chmod(0o600)
            temporary.replace(path)
        except OSError:
            return

    def _cache_path(self, args: list[str]) -> Path:
        return self.cache_dir / "github" / f"{self._cache_key(args)}.json"

    def _cache_key(self, args: list[str]) -> str:
        host = os.environ.get("GH_HOST") or os.environ.get("GITHUB_HOST") or ""
        material = json.dumps([host, args], separators=(",", ":"))
        return hashlib.sha256(material.encode()).hexdigest()


def default_cache_dir() -> Path:
    """Return the user cache directory without creating it."""
    configured = os.environ.get("QUICK_STATUS_CACHE_DIR")
    if configured:
        return Path(configured).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".cache"
    return base / "quick-status"


def bounded_error(result: CommandResult) -> str:
    """Return a compact non-secret command error for snapshot output."""
    if result.unavailable:
        return "gh is not installed"
    if result.timed_out:
        return result.stderr.strip() or "GitHub query timed out"
    detail = result.stderr.strip() or result.stdout.strip()
    if not detail:
        detail = f"exit code {result.exit_code}"
    return detail.replace("\n", " ")[:300]


def _decode(
    text: str,
    *,
    expected: str,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if expected == "object":
        return data if isinstance(data, dict) else None
    if not isinstance(data, list):
        return None
    return [item for item in data if isinstance(item, dict)]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
