"""Append one hash-chained JSON line per task invocation to an optional rotating audit log."""

import fcntl
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from makefile_mcp.models import AuditConfig, TaskDefinition, TaskResult

MASK = "***"
TAIL_CHARS = 2000
# The newest lines sit in the last few KiB; records are bounded by TAIL_CHARS plus metadata.
_TAIL_READ_BYTES = 64 * 1024


def line_hash(line: str) -> str:
    """Return the chain hash of one audit line, without its newline."""
    return "sha256:" + hashlib.sha256(line.encode("utf-8")).hexdigest()


def _last_line(path: Path) -> str | None:
    """Return the last non-empty line of *path*, or ``None`` when it has none."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - _TAIL_READ_BYTES))
            lines = handle.read().decode("utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return None
    return next((line for line in reversed(lines) if line.strip()), None)


def log_files(path: Path, backup_count: int) -> list[Path]:
    """Return existing log files oldest first: ``path.N`` ... ``path.1``, then ``path``."""
    rotated = [Path(f"{path}.{index}") for index in range(backup_count, 0, -1)]
    return [file for file in (*rotated, path) if file.is_file()]


def verify_chain(files: list[Path]) -> str | None:
    """Return the first chain break across *files* (oldest first), or ``None`` if intact.

    The chain starts at the first record carrying ``prev_sha256``; earlier lines predate it.
    The oldest surviving record is the anchor, since rotation drops its predecessor.
    """
    previous: str | None = None
    started = False
    for file in files:
        for number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                return f"{file.name}:{number}: not valid JSON"
            if "prev_sha256" not in record:
                if started:
                    return f"{file.name}:{number}: record has no prev_sha256"
            elif started and record["prev_sha256"] != line_hash(previous or ""):
                return f"{file.name}:{number}: prev_sha256 does not match the previous record"
            else:
                started = True
            previous = line
    return None


class AuditLog:
    """Write audit records; a no-op when no audit path is configured."""

    def __init__(self, root: Path, config: AuditConfig | None):
        """Prepare the configured log file relative to the repository root."""
        self._config = config
        self._path: Path | None = None
        if config is not None:
            self._path = root / config.path
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        task: TaskDefinition,
        arguments: dict[str, str],
        *,
        approval: str,
        result: TaskResult | None = None,
        preview: bool = False,
        status: str = "refused",
        reason: str | None = None,
    ) -> None:
        """Append one invocation record with secret values masked.

        Without a *result*, the record carries *status* (``refused`` or ``cancelled``).
        """
        if self._path is None:
            return
        secret_names = {name for name, spec in task.variables.items() if spec.secret}
        secrets = [value for name, value in arguments.items() if name in secret_names and value]
        output = (result.stdout + result.stderr) if result else ""
        for secret in secrets:
            output = output.replace(secret, MASK)
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "task": task.name,
            "context": task.context,
            "arguments": {
                name: MASK if name in secret_names else value for name, value in arguments.items()
            },
            "risk": task.risk.value,
            "approval": approval,
            "preview": preview,
            "status": result.status.value if result else status,
            "exit_code": result.exit_code if result else None,
            "duration_ms": result.duration_ms if result else 0,
            "output_bytes": len(output.encode("utf-8")),
            "output_tail": output[-TAIL_CHARS:],
        }
        if reason is not None:
            entry["reason"] = reason
        self._write(entry)

    def refuse(self, task: str, context: str, arguments: object, *, reason: str) -> None:
        """Record a call refused before its task contract was known or its inputs were valid.

        Secrecy is unknown at this point, so only argument names are kept, never values.
        """
        if self._path is None:
            return
        names = sorted(str(name) for name in arguments) if isinstance(arguments, dict) else []
        self._write(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "task": task,
                "context": context,
                "arguments": dict.fromkeys(names, MASK),
                "risk": None,
                "approval": "not_evaluated",
                "status": "refused",
                "reason": reason,
            }
        )

    def _write(self, entry: dict[str, object]) -> None:
        """Chain *entry* to the newest record on disk, rotate if needed, and append it.

        Everything happens under one lock, and the file is reopened for each record, so the
        CLI and a server writing the same log can neither fork the chain nor write to a file
        another process has just rotated away.
        """
        assert self._path is not None and self._config is not None
        path = self._path
        with Path(f"{path}.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            previous = _last_line(path) or _last_line(Path(f"{path}.1"))
            entry["prev_sha256"] = line_hash(previous) if previous is not None else None
            line = json.dumps(entry, sort_keys=True) + "\n"
            size = path.stat().st_size if path.exists() else 0
            if self._config.backup_count and size and size + len(line) > self._config.max_bytes:
                self._rotate()
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)

    def _rotate(self) -> None:
        """Shift ``path`` to ``path.1``, ``path.1`` to ``path.2``, and drop the oldest."""
        assert self._path is not None and self._config is not None
        for index in range(self._config.backup_count - 1, 0, -1):
            source = Path(f"{self._path}.{index}")
            if source.exists():
                source.replace(Path(f"{self._path}.{index + 1}"))
        self._path.replace(Path(f"{self._path}.1"))
