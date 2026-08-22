"""Orchestrate one authorized Make task through the bounded process boundary."""

import os
from datetime import UTC, datetime
from pathlib import Path

from make_mcp.catalog import Catalog, Contexts
from make_mcp.errors import ExecutionStartError
from make_mcp.filesystem import FileContextLock
from make_mcp.inputs import make_variables, string_input_file, validate_variables
from make_mcp.models import (
    EnvironmentConfig,
    MakeMcpConfig,
    TaskDefinition,
    TaskResult,
    TaskStatus,
)
from make_mcp.process import SubprocessRunner
from make_mcp.syntax import MAKE_MCP_INPUT_VARIABLE


def build_make_argv(
    task_name: str,
    *,
    makefile: Path,
    variables: dict[str, str],
    string_input_file: Path | None = None,
    preview: bool = False,
) -> list[str]:
    """Build the exact Make invocation from already-authorized, already-validated inputs."""
    assignments = [f"{key}={value}" for key, value in sorted(variables.items())]
    if string_input_file is not None:
        # Only this generated safe path crosses Make for arbitrary-string inputs; the string
        # contents themselves remain in JSON. MAKE_MCP_INPUT is reserved from user config.
        assignments.append(f"{MAKE_MCP_INPUT_VARIABLE}={string_input_file}")

    # `-f` is security-relevant: discovery inspects `Makefile`, so execution must not let
    # GNU Make silently prefer a sibling `GNUmakefile` or lowercase `makefile` instead.
    argv = ["make", "--no-print-directory"]
    if preview:
        # GNU Make --dry-run is a preview, not a sandbox: Makefile expansion, remaking included
        # Makefiles, and recursive $(MAKE) recipes may still execute side effects.
        argv.append("--dry-run")
    return [*argv, "-f", str(makefile), task_name, *assignments]


def build_environment(config: EnvironmentConfig) -> dict[str, str]:
    """Construct the explicitly inherited/configured child environment."""
    env = {name: os.environ[name] for name in config.inherit if name in os.environ}
    env.update(config.allow)
    return env


def _status(*, timed_out: bool, exit_code: int | None) -> TaskStatus:
    if timed_out:
        return TaskStatus.TIMEOUT
    if exit_code == 0:
        return TaskStatus.PASSED
    return TaskStatus.FAILED


class TaskExecutor:
    """Authorize, prepare, run, and normalize one Make task invocation."""

    def __init__(
        self,
        *,
        root: Path,
        config: MakeMcpConfig,
        contexts: Contexts,
        catalog: Catalog,
        runner: SubprocessRunner,
        lock: FileContextLock,
    ):
        """Create an executor from the shared catalog, process runner, and context lock."""
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
        *,
        preview: bool = False,
    ) -> TaskResult:
        """Execute one callable task and return a stable bounded result."""
        task = self.catalog.describe(task_name, context)
        project_context = self.contexts.resolve(context)
        validated = validate_variables(
            task,
            variables or {},
            root=self.root,
            cwd=project_context.directory,
            input_limit_bytes=self.config.defaults.input_limit_bytes,
        )

        try:
            # Catalog discovery is always against this exact conventional Makefile. Resolve it
            # inside the normalized preparation boundary so a deletion/permission race becomes
            # a stable ERROR result instead of leaking a raw filesystem exception.
            makefile = (project_context.directory / "Makefile").resolve(strict=True)
            with self.lock.acquire(context, directory=project_context.directory):
                # The JSON payload is intentionally scoped inside the execution lock and process
                # lifetime. It cannot outlive the task or become shared mutable state.
                with string_input_file(
                    task,
                    validated,
                    input_limit_bytes=self.config.defaults.input_limit_bytes,
                ) as payload_file:
                    process = await self.runner.run(
                        argv=build_make_argv(
                            task.name,
                            makefile=makefile,
                            variables=make_variables(task, validated),
                            string_input_file=payload_file,
                            preview=preview,
                        ),
                        cwd=project_context.directory,
                        timeout_seconds=task.timeout_seconds,
                        env=build_environment(self.config.environment),
                        output_limit_bytes=self.config.defaults.output_limit_bytes,
                    )
        except ExecutionStartError as exc:
            message = str(exc)
        except OSError as exc:
            # Expected filesystem failures during Makefile resolution, lock creation, or the
            # private JSON lifecycle are operational errors, not Python tracebacks for callers.
            message = f"execution preparation failed: {exc}"
        else:
            message = None

        if message is not None:
            now = datetime.now(UTC)
            return TaskResult(
                task=task.name,
                context=context,
                status=TaskStatus.ERROR,
                exit_code=None,
                started_at=now,
                completed_at=now,
                duration_ms=0,
                stderr=message,
                preview=preview,
            )

        duration_ms = max(
            0,
            int((process.completed_at - process.started_at).total_seconds() * 1000),
        )
        return TaskResult(
            task=task.name,
            context=context,
            status=_status(
                timed_out=process.timed_out,
                exit_code=process.exit_code,
            ),
            exit_code=process.exit_code,
            started_at=process.started_at,
            completed_at=process.completed_at,
            duration_ms=duration_ms,
            stdout=process.stdout,
            stderr=process.stderr,
            truncated=process.truncated,
            preview=preview,
        )
