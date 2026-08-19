"""Bounded subprocess execution for already-authorized Make tasks."""

import asyncio
import os
import signal
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from makefile_mcp.errors import ExecutionStartError
from makefile_mcp.models import ProcessResult

# Timeout/cancellation first terminates the process group, then gives pipe readers only a
# short bounded interval to observe EOF. A detached descendant must not keep an MCP call open.
_TERMINATION_GRACE_SECONDS = 1.0
_PIPE_DRAIN_GRACE_SECONDS = 0.25


async def _read_bounded(stream: asyncio.StreamReader, limit: int) -> tuple[str, bool]:
    chunks: list[bytes] = []
    kept = 0
    truncated = False
    try:
        while True:
            chunk = await stream.read(64 * 1024)
            if not chunk:
                break
            if kept < limit:
                remaining = limit - kept
                chunks.append(chunk[:remaining])
                kept += min(len(chunk), remaining)
                truncated = truncated or len(chunk) > remaining
            else:
                # Continue draining after the retention limit so a chatty child cannot block
                # on a full pipe; only retained memory is bounded, not the drain operation.
                truncated = True
    except asyncio.CancelledError:
        # When an escaped descendant keeps the descriptor open, preserve bytes already read and
        # mark the capture truncated rather than waiting forever for EOF.
        truncated = True
    return b"".join(chunks).decode("utf-8", errors="replace"), truncated


async def _terminate_process_tree(
    process: asyncio.subprocess.Process,
    grace_seconds: float = _TERMINATION_GRACE_SECONDS,
) -> None:
    # Signal the group even if the Make leader crossed the exit boundary just before this
    # function ran; descendants may still be alive in the dedicated process group.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        if process.returncode is None:
            await process.wait()
        return

    if process.returncode is None:
        with suppress(TimeoutError):
            await asyncio.wait_for(process.wait(), timeout=grace_seconds)

    # Once the leader has exited (or the TERM grace expired), escalate any remaining members.
    # Waiting only for the leader is not proof that the whole process group stopped.
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    if process.returncode is None:
        await process.wait()


async def _terminate_residual_process_group(
    process_group_id: int,
    grace_seconds: float = _PIPE_DRAIN_GRACE_SECONDS,
) -> None:
    """Terminate background descendants that remained in the task process group."""
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        return
    await asyncio.sleep(grace_seconds)
    with suppress(ProcessLookupError):
        os.killpg(process_group_id, signal.SIGKILL)


async def _finish_reader(
    task: asyncio.Task[tuple[str, bool]],
) -> tuple[str, bool]:
    """Collect a pipe without allowing inherited descriptors to defeat task bounds."""
    try:
        # Shield prevents wait_for from discarding the reader's already-captured bytes.
        return await asyncio.wait_for(asyncio.shield(task), timeout=_PIPE_DRAIN_GRACE_SECONDS)
    except TimeoutError:
        task.cancel()
        return await task


async def _close_process_transport(process: asyncio.subprocess.Process) -> None:
    """Close asyncio's subprocess transport before its event loop can be torn down.

    ``asyncio.subprocess.Process`` exposes no public ``close()`` method. CPython otherwise
    relies on transport finalization, which can run after ``asyncio.run()`` has closed its
    loop and emit ``BaseSubprocessTransport.__del__`` warnings on Python 3.12.
    """
    transport = getattr(process, "_transport", None)
    if transport is None:
        return
    transport.close()
    # Let pipe connection_lost callbacks run while the event loop is still alive.
    await asyncio.sleep(0)


class SubprocessRunner:
    """Run one argv-based child process with bounded lifecycle and output retention."""

    async def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: int,
        env: dict[str, str],
        output_limit_bytes: int,
    ) -> ProcessResult:
        """Execute *argv* in a dedicated process group and return a bounded result."""
        started = datetime.now(UTC)
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # A dedicated session gives Make and normal descendants one process group that
                # can be terminated together on timeout/cancellation.
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            raise ExecutionStartError(f"could not start Make: {exc}") from exc

        assert process.stdout is not None
        assert process.stderr is not None
        stdout_task = asyncio.create_task(_read_bounded(process.stdout, output_limit_bytes))
        stderr_task = asyncio.create_task(_read_bounded(process.stderr, output_limit_bytes))
        timed_out = False
        cancelled_error: asyncio.CancelledError | None = None
        try:
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
            except TimeoutError:
                timed_out = True
                await _terminate_process_tree(process)
            except asyncio.CancelledError as exc:
                # Cancellation is a control-flow signal, not a TaskResult outcome. Clean the
                # normal process group and bounded pipe readers, then re-raise so MCP/embedding
                # callers observe cancellation instead of a false successful tool completion.
                cancelled_error = exc
                await _terminate_process_tree(process)

            if not timed_out and cancelled_error is None:
                # A successful Make process may leave recipe-spawned background children in its
                # process group. Makefile MCP tasks are bounded foreground jobs,
                # not daemon launchers.
                await _terminate_residual_process_group(process.pid)

            # Always bound final pipe draining. Even a recipe that exits successfully can spawn a
            # detached process that inherits stdout/stderr and otherwise keeps readers alive.
            stdout, out_truncated = await _finish_reader(stdout_task)
            stderr, err_truncated = await _finish_reader(stderr_task)
            if cancelled_error is not None:
                raise cancelled_error

            completed = datetime.now(UTC)
            return ProcessResult(
                exit_code=process.returncode,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                truncated=out_truncated or err_truncated,
                started_at=started,
                completed_at=completed,
            )
        finally:
            # Explicit transport closure prevents CPython 3.12 from finalizing pipe transports
            # after pytest/asyncio has already closed the event loop.
            for reader_task in (stdout_task, stderr_task):
                if not reader_task.done():
                    reader_task.cancel()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            await _close_process_transport(process)
