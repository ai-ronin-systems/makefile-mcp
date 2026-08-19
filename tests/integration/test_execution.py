import asyncio

import pytest


def test_pass_and_fail_are_normal_results(app_for):
    app = app_for(
        ".PHONY: ok fail\n"
        "ok: ## OK\n\t@echo hello\n"
        "fail: ## Fail\n\t@echo bad >&2; exit 7\n"
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
        "schema_version: 1\ndefaults:\n  output_limit_bytes: 4096\n",
    )
    result = await app.run_task("noisy")
    assert result.status == "passed"
    assert result.truncated is True
    assert len(result.stdout.encode()) <= 4096


@pytest.mark.asyncio
async def test_cancellation_terminates_task(app_for):
    app = app_for(".PHONY: slow\nslow: ## Slow\n\t@sleep 30\n")
    task = asyncio.create_task(app.run_task("slow"))
    await asyncio.sleep(0.1)
    task.cancel()
    result = await task
    assert result.status == "cancelled"
