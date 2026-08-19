"""Validate an exposed task request and execute it through the bounded process boundary."""

import os
import re
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from make_mcp.core.catalog import Catalog, Contexts
from make_mcp.errors import ExecutionStartError, VariableValidationError
from make_mcp.infrastructure.filesystem import ensure_within_root
from make_mcp.models import (
    EnvironmentConfig,
    MakeMcpConfig,
    ProcessResult,
    TaskDefinition,
    TaskResult,
    TaskStatus,
    TaskVariable,
    VariableType,
)

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ProcessRunner(Protocol):
    async def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: int,
        env: dict[str, str],
        output_limit_bytes: int,
    ) -> ProcessResult: ...


class ContextLock(Protocol):
    def acquire(self, context_name: str) -> AbstractContextManager[None]: ...


def _reject_controls(value: str) -> None:
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise VariableValidationError("variable values may not contain control characters")


def _convert_variable(spec: TaskVariable, raw: str, *, root: Path, cwd: Path) -> str:
    _reject_controls(raw)
    if spec.type == VariableType.STRING:
        return raw
    if spec.type == VariableType.INTEGER:
        try:
            return str(int(raw, 10))
        except ValueError as exc:
            raise VariableValidationError(f"expected integer, got {raw!r}") from exc
    if spec.type == VariableType.BOOLEAN:
        lowered = raw.lower()
        if lowered in {"1", "true", "yes", "on"}:
            return "true"
        if lowered in {"0", "false", "no", "off"}:
            return "false"
        raise VariableValidationError(f"expected boolean, got {raw!r}")
    if spec.type == VariableType.ENUM:
        if raw not in spec.values:
            raise VariableValidationError(f"expected one of {spec.values}, got {raw!r}")
        return raw
    if spec.type == VariableType.PATH:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = cwd / candidate
        return str(ensure_within_root(root, candidate, must_exist=False))
    raise VariableValidationError(f"unsupported variable type: {spec.type}")


def validate_variables(
    task: TaskDefinition,
    supplied: dict[str, str],
    *,
    root: Path,
    cwd: Path,
) -> dict[str, str]:
    unknown = sorted(set(supplied) - set(task.variables))
    if unknown:
        raise VariableValidationError(f"undeclared variables: {', '.join(unknown)}")

    result: dict[str, str] = {}
    for name, spec in task.variables.items():
        if not _NAME.fullmatch(name):
            raise VariableValidationError(f"invalid declared variable name: {name}")
        if name in supplied:
            result[name] = _convert_variable(spec, supplied[name], root=root, cwd=cwd)
        elif spec.default is not None:
            result[name] = _convert_variable(spec, str(spec.default), root=root, cwd=cwd)
        elif spec.required:
            raise VariableValidationError(f"missing required variable: {name}")
    return result


def build_make_argv(task_name: str, variables: dict[str, str]) -> list[str]:
    assignments = [f"{key}={value}" for key, value in sorted(variables.items())]
    return ["make", "--no-print-directory", task_name, *assignments]


def build_environment(config: EnvironmentConfig) -> dict[str, str]:
    env = {name: os.environ[name] for name in config.inherit if name in os.environ}
    env.update(config.allow)
    return env


def _status(process: ProcessResult) -> TaskStatus:
    if process.cancelled:
        return TaskStatus.CANCELLED
    if process.timed_out:
        return TaskStatus.TIMEOUT
    if process.exit_code == 0:
        return TaskStatus.PASSED
    return TaskStatus.FAILED


class TaskExecutor:
    def __init__(
        self,
        *,
        root: Path,
        config: MakeMcpConfig,
        contexts: Contexts,
        catalog: Catalog,
        runner: ProcessRunner,
        lock: ContextLock,
    ):
        self.root = root
        self.config = config
        self.contexts = contexts
        self.catalog = catalog
        self.runner = runner
        self.lock = lock

    async def run(
        self,
        task_name: str,
        variables: dict[str, str] | None = None,
        context: str = "root",
    ) -> TaskResult:
        task = self.catalog.describe(task_name, context)
        project_context = self.contexts.resolve(context)
        validated = validate_variables(
            task,
            variables or {},
            root=self.root,
            cwd=project_context.directory,
        )
        try:
            with self.lock.acquire(context):
                process = await self.runner.run(
                    argv=build_make_argv(task.name, validated),
                    cwd=project_context.directory,
                    timeout_seconds=task.timeout_seconds,
                    env=build_environment(self.config.environment),
                    output_limit_bytes=self.config.defaults.output_limit_bytes,
                )
        except ExecutionStartError as exc:
            now = datetime.now(UTC)
            return TaskResult(
                task=task.name,
                context=context,
                status=TaskStatus.ERROR,
                exit_code=None,
                started_at=now,
                completed_at=now,
                duration_ms=0,
                stderr=str(exc),
            )

        duration_ms = max(
            0,
            int((process.completed_at - process.started_at).total_seconds() * 1000),
        )
        return TaskResult(
            task=task.name,
            context=context,
            status=_status(process),
            exit_code=process.exit_code,
            started_at=process.started_at,
            completed_at=process.completed_at,
            duration_ms=duration_ms,
            stdout=process.stdout,
            stderr=process.stderr,
            truncated=process.truncated,
        )
