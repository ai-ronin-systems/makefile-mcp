"""Repository path confinement, root detection, fingerprints, and context locks."""

import fcntl
import hashlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from make_mcp.errors import ConfigurationError, TaskBusyError, UnsafePathError

_SAFE_LOCK_NAME = re.compile(r"[^A-Za-z0-9_.-]+")

# One row includes lexical-path metadata plus resolved-target metadata. This notices ordinary
# edits, same-size edits with restored mtimes, and symlink retargeting without hashing files.
Fingerprint = tuple[
    tuple[str, int, int, int, int, str, int, int, int, int],
    ...,
]


def detect_repository_root(start: Path) -> Path:
    """Return the nearest repository/config/Makefile boundary above *start*."""
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    candidates = (current, *current.parents)

    # Walk by directory proximity, not by marker type. Otherwise a parent
    # `.make-mcp.yaml` could outrank a nearer child `.git` repository and bind
    # the process to the wrong project's authorization policy.
    for candidate in candidates:
        if (candidate / ".make-mcp.yaml").exists() or (candidate / ".git").exists():
            return candidate

    # A standalone Makefile without Git/config is still a valid local project,
    # but only after repository/config boundaries have been exhausted.
    for candidate in candidates:
        if (candidate / "Makefile").exists():
            return candidate
    raise ConfigurationError(f"could not detect repository root from {start}")


def ensure_within_root(root: Path, path: Path, *, must_exist: bool = True) -> Path:
    """Resolve *path* and require it to remain inside the trusted repository root."""
    try:
        root = root.resolve(strict=True)
        resolved = path.resolve(strict=must_exist)
    except FileNotFoundError as exc:
        raise UnsafePathError(f"path does not exist: {path}") from exc
    except (OSError, RuntimeError) as exc:
        raise UnsafePathError(f"could not resolve path safely: {path}: {exc}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError(f"path escapes repository root: {path}") from exc
    return resolved


def fingerprint(paths: list[Path]) -> Fingerprint:
    """Return a lightweight fingerprint that also detects symlink and inode changes."""
    rows: list[tuple[str, int, int, int, int, str, int, int, int, int]] = []
    for path in sorted(set(paths), key=str):
        try:
            lexical = path.lstat()
        except FileNotFoundError:
            rows.append((str(path), -1, -1, -1, -1, "", -1, -1, -1, -1))
            continue

        resolved_path = path.resolve(strict=False)
        try:
            target = path.stat()
            target_values = (
                target.st_mtime_ns,
                target.st_ctime_ns,
                target.st_size,
                target.st_ino,
            )
        except FileNotFoundError:
            target_values = (-1, -1, -1, -1)

        rows.append(
            (
                str(path),
                lexical.st_mtime_ns,
                lexical.st_ctime_ns,
                lexical.st_size,
                lexical.st_ino,
                str(resolved_path),
                *target_values,
            )
        )
    return tuple(rows)


class FileContextLock:
    """Cross-process, non-blocking one-task-per-physical-context lock for POSIX hosts."""

    def __init__(self, root: Path):
        """Create a lock manager rooted under ``.make-mcp/locks``."""
        self._directory = root / ".make-mcp" / "locks"

    @contextmanager
    def acquire(
        self,
        context_name: str,
        *,
        directory: Path | None = None,
    ) -> Iterator[None]:
        """Acquire a non-blocking exclusive lock for one execution context."""
        self._directory.mkdir(parents=True, exist_ok=True)
        if directory is None:
            # Compatibility for direct/unit use. Runtime execution always supplies the resolved
            # physical directory so two configured aliases cannot bypass serialization.
            lock_name = _SAFE_LOCK_NAME.sub("_", context_name)
        else:
            identity = str(directory).encode("utf-8")
            lock_name = "context-" + hashlib.sha256(identity).hexdigest()[:16]
        path = self._directory / f"{lock_name}.lock"
        with path.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise TaskBusyError(f"context already has an active task: {context_name}") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
