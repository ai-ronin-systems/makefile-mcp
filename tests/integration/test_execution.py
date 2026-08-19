import asyncio

import pytest


def test_pass_and_fail_are_normal_results(app_for):
    app = app_for(
        ".PHONY: ok fail\nok: ## OK\n\t@echo hello\nfail: ## Fail\n\t@echo bad >&2; exit 7\n",
        "schema_version: 1\ntasks:\n  ok: {}\n  fail: {}\n",
    )
    passed = asyncio.run(app.run_task("ok"))
    failed = asyncio.run(app.run_task("fail"))
    assert passed.status == "passed" and passed.exit_code == 0 and "hello" in passed.stdout
    assert failed.status == "failed" and failed.exit_code == 2 and "bad" in failed.stderr


@pytest.mark.asyncio
async def test_timeout_is_enforced(app_for):
    app = app_for(
        ".PHONY: slow\nslow: ## Slow\n\t@sleep 30\n",
        "schema_version: 1\ntasks:\n  slow:\n    timeout_seconds: 1\n",
    )
    result = await app.run_task("slow")
    assert result.status == "timeout"


@pytest.mark.asyncio
async def test_output_is_bounded_and_drained(app_for):
    app = app_for(
        ".PHONY: noisy\nnoisy: ## Noisy\n\t@python3 -c 'print(\"x\" * 20000)'\n",
        "schema_version: 1\ndefaults:\n  output_limit_bytes: 4096\ntasks:\n  noisy: {}\n",
    )
    result = await app.run_task("noisy")
    assert result.status == "passed"
    assert result.truncated is True
    assert len(result.stdout.encode()) <= 4096


@pytest.mark.asyncio
async def test_cancellation_terminates_task_and_propagates(app_for):
    app = app_for(
        ".PHONY: slow\nslow: ## Slow\n\t@(sleep 1; touch cancellation-marker) & sleep 30\n",
        "schema_version: 1\ntasks:\n  slow: {}\n",
    )
    task = asyncio.create_task(app.run_task("slow"))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Cancellation must terminate the normal recipe process group, not merely unwind Python.
    await asyncio.sleep(1.1)
    assert not (app.root / "cancellation-marker").exists()


@pytest.mark.asyncio
async def test_execution_uses_exact_inspected_makefile(app_for):
    app = app_for(
        ".PHONY: test\ntest:\n\t@echo SAFE_MAKEFILE\n",
        "schema_version: 1\ntasks:\n  test: {}\n",
    )
    # GNU Make normally prefers GNUmakefile over Makefile. Makefile MCP must not: it authorized
    # the target discovered from Makefile, so execution is explicitly pinned to that file.
    (app.root / "GNUmakefile").write_text(
        ".PHONY: test\ntest:\n\t@echo WRONG_GNUMAKEFILE\n",
        encoding="utf-8",
    )
    result = await app.run_task("test")
    assert result.status == "passed"
    assert "SAFE_MAKEFILE" in result.stdout
    assert "WRONG_GNUMAKEFILE" not in result.stdout


@pytest.mark.asyncio
async def test_detached_pipe_holder_cannot_defeat_timeout(app_for):
    import time

    app = app_for(
        ".PHONY: detach\n"
        "detach:\n"
        "\t@python3 -c 'import os,time; os.setsid(); time.sleep(4)' & sleep 30\n",
        "schema_version: 1\ntasks:\n  detach:\n    timeout_seconds: 1\n",
    )
    started = time.monotonic()
    result = await app.run_task("detach")
    elapsed = time.monotonic() - started
    assert result.status == "timeout"
    # 1s task timeout + 1s termination grace + 250ms drain grace, with scheduler margin.
    assert elapsed < 3.0


@pytest.mark.asyncio
async def test_nested_literal_include_discovery_matches_make_execution(repo):
    root = repo(
        "include sub/one.mk\n",
        "schema_version: 1\ntasks:\n  deploy: {}\n",
    )
    sub = root / "sub"
    sub.mkdir()
    (sub / "one.mk").write_text("include two.mk\n", encoding="utf-8")
    (sub / "two.mk").write_text("deploy:\n\t@echo WRONG_NESTED_FILE\n", encoding="utf-8")
    (root / "two.mk").write_text("deploy:\n\t@echo ACTUAL_ROOT_FILE\n", encoding="utf-8")

    from makefile_mcp.app import build_application

    result = await build_application(root).run_task("deploy")
    assert result.status == "passed"
    assert "ACTUAL_ROOT_FILE" in result.stdout
    assert "WRONG_NESTED_FILE" not in result.stdout


@pytest.mark.asyncio
async def test_lock_filesystem_failure_is_normalized_to_error_result(app_for):
    app = app_for(
        ".PHONY: ok\nok:\n\t@true\n",
        "schema_version: 1\ntasks:\n  ok: {}\n",
    )
    # A file where the lock directory's parent must be causes mkdir/open to fail. This is an
    # operational preparation error and must not leak a raw OSError to CLI/MCP callers.
    (app.root / ".makefile-mcp").write_text("not a directory", encoding="utf-8")

    result = await app.run_task("ok")
    assert result.status == "error"
    assert "execution preparation failed" in result.stderr


@pytest.mark.asyncio
async def test_task_stdin_is_closed_instead_of_inheriting_mcp_protocol_input(app_for):
    app = app_for(
        ".PHONY: stdin-check\n"
        "stdin-check:\n"
        "\t@if read value; then echo HAS_STDIN; else echo EOF; fi\n",
        "schema_version: 1\ntasks:\n  stdin-check: {}\n",
    )
    result = await app.run_task("stdin-check")
    assert result.status == "passed"
    assert "EOF" in result.stdout
    assert "HAS_STDIN" not in result.stdout


@pytest.mark.asyncio
async def test_background_child_in_task_process_group_cannot_outlive_success(app_for, tmp_path):
    marker = tmp_path / "ESCAPED"
    app = app_for(
        f".PHONY: bg\nbg:\n\t@(sleep 1; touch {marker}) >/dev/null 2>&1 &\n",
        "schema_version: 1\ntasks:\n  bg: {}\n",
    )
    result = await app.run_task("bg")
    assert result.status == "passed"
    await asyncio.sleep(1.2)
    assert not marker.exists()


@pytest.mark.asyncio
async def test_preview_uses_make_dry_run_without_executing_normal_recipe(app_for):
    app = app_for(
        ".PHONY: write\nwrite:\n\t@touch preview-marker\n",
        "schema_version: 1\ntasks:\n  write: {}\n",
    )

    result = await app.run_task("write", preview=True)

    assert result.status == "passed"
    assert result.preview is True
    assert "touch preview-marker" in result.stdout
    assert not (app.root / "preview-marker").exists()


def test_subprocess_transport_is_closed_before_asyncio_run_loop_teardown(tmp_path):
    """A completed Makefile MCP process must not leave asyncio pipe transports
    for GC after loop close.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    source_root = Path(__file__).parents[2] / "src"
    script = """
import asyncio
import gc
import sys
from pathlib import Path

from makefile_mcp.process import SubprocessRunner

unraisable = []
sys.unraisablehook = lambda args: unraisable.append(args)

async def main():
    result = await SubprocessRunner().run(
        argv=["sh", "-c", "printf ok"],
        cwd=Path.cwd(),
        timeout_seconds=5,
        env={"PATH": "/usr/bin:/bin"},
        output_limit_bytes=1024,
    )
    assert result.stdout == "ok"

asyncio.run(main())
gc.collect()
assert not unraisable, [str(item.exc_value) for item in unraisable]
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(source_root)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_subprocess_start_failure_is_normalized(tmp_path):
    from makefile_mcp.errors import ExecutionStartError
    from makefile_mcp.process import SubprocessRunner

    with pytest.raises(ExecutionStartError, match="could not start Make"):
        await SubprocessRunner().run(
            argv=["/definitely/not/a/real/executable"],
            cwd=tmp_path,
            timeout_seconds=1,
            env={"PATH": "/usr/bin:/bin"},
            output_limit_bytes=4096,
        )
