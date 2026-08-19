"""Repository path confinement, root detection, fingerprints, and context locks."""

import fcntl
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from make_mcp.errors import ConfigurationError, TaskBusyError, UnsafePathError

_SAFE_LOCK_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def detect_repository_root(start: Path) -> Path:
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    candidates = (current, *current.parents)
    for marker in (".make-mcp.yaml", ".git"):
        for candidate in candidates:
            if (candidate / marker).exists():
                return candidate
    for candidate in candidates:
        if (candidate / "Makefile").exists():
            return candidate
    raise ConfigurationError(f"could not detect repository root from {start}")


def ensure_within_root(root: Path, path: Path, *, must_exist: bool = True) -> Path:
    root = root.resolve(strict=True)
    try:
        resolved = path.resolve(strict=must_exist)
    except FileNotFoundError as exc:
        raise UnsafePathError(f"path does not exist: {path}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError(f"path escapes repository root: {path}") from exc
    return resolved


def fingerprint(paths: list[Path]) -> tuple[tuple[str, int, int], ...]:
    rows: list[tuple[str, int, int]] = []
    for path in sorted(set(paths)):
        try:
            stat = path.stat()
            rows.append((str(path), stat.st_mtime_ns, stat.st_size))
        except FileNotFoundError:
            rows.append((str(path), -1, -1))
    return tuple(rows)


class FileContextLock:
    """Cross-process, non-blocking one-task-per-context lock for POSIX hosts."""

    def __init__(self, root: Path):
        self._directory = root / ".make-mcp" / "locks"

    @contextmanager
    def acquire(self, context_name: str) -> Iterator[None]:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{_SAFE_LOCK_NAME.sub('_', context_name)}.lock"
        with path.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise TaskBusyError(f"context already has an active task: {context_name}") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
