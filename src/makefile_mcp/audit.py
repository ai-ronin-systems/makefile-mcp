"""Append one JSON line per task invocation to an optional rotating audit log."""

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from makefile_mcp.models import AuditConfig, TaskDefinition, TaskResult

MASK = "***"
TAIL_CHARS = 2000


class AuditLog:
    """Write audit records; a no-op when no audit path is configured."""

    def __init__(self, root: Path, config: AuditConfig | None):
        """Open (lazily) the configured log file relative to the repository root."""
        self._handler = None
        if config is not None:
            path = root / config.path
            path.parent.mkdir(parents=True, exist_ok=True)
            self._handler = RotatingFileHandler(
                path,
                maxBytes=config.max_bytes,
                backupCount=config.backup_count,
                encoding="utf-8",
                delay=True,
            )

    def record(
        self,
        task: TaskDefinition,
        arguments: dict[str, str],
        *,
        approval: str,
        result: TaskResult | None = None,
        preview: bool = False,
    ) -> None:
        """Append one invocation record with secret values masked."""
        if self._handler is None:
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
            "status": result.status.value if result else "refused",
            "exit_code": result.exit_code if result else None,
            "duration_ms": result.duration_ms if result else 0,
            "output_bytes": len(output.encode("utf-8")),
            "output_tail": output[-TAIL_CHARS:],
        }
        self._handler.handle(logging.makeLogRecord({"msg": json.dumps(entry, sort_keys=True)}))
