"""Bounded subprocess execution for already-authorized Make tasks."""

import asyncio
import os
import signal
from datetime import UTC, datetime
from pathlib import Path

from make_mcp.errors import ExecutionStartError
from make_mcp.models import ProcessResult


async def _read_bounded(stream: asyncio.StreamReader, limit: int) -> tuple[str, bool]:
    chunks: list[bytes] = []
    kept = 0
    truncated = False
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
            truncated = True
    return b"".join(chunks).decode("utf-8", errors="replace"), truncated


async def _terminate_process_tree(
    process: asyncio.subprocess.Process, grace_seconds: float = 2.0
) -> None:
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=grace_seconds)
        return
    except TimeoutError:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    await process.wait()


class SubprocessRunner:
    async def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: int,
        env: dict[str, str],
        output_limit_bytes: int,
    ) -> ProcessResult:
        started = datetime.now(UTC)
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            raise ExecutionStartError(f"could not start Make: {exc}") from exc

        assert process.stdout is not None
        assert process.stderr is not None
        stdout_task = asyncio.create_task(_read_bounded(process.stdout, output_limit_bytes))
        stderr_task = asyncio.create_task(_read_bounded(process.stderr, output_limit_bytes))
        timed_out = False
        cancelled = False
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        except TimeoutError:
            timed_out = True
            await _terminate_process_tree(process)
        except asyncio.CancelledError:
            cancelled = True
            await _terminate_process_tree(process)

        stdout, out_truncated = await stdout_task
        stderr, err_truncated = await stderr_task
        completed = datetime.now(UTC)
        return ProcessResult(
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            cancelled=cancelled,
            truncated=out_truncated or err_truncated,
            started_at=started,
            completed_at=completed,
        )
