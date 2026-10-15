import asyncio

import pytest

from makefile_mcp.app import build_application
from makefile_mcp.errors import ApprovalRequired, TaskNotRunnable
from makefile_mcp.mcp.presentation import build_direct_tools

AUTO_MAKEFILE = ".PHONY: test deploy\ntest:\n\t@echo testing\ndeploy:\n\t@echo deploying\n"

DANGEROUS = "schema_version: 1\ntasks:\n  deploy:\n    risk: dangerous\n"
DEPLOY_MAKEFILE = ".PHONY: deploy\ndeploy:\n\t@echo deploying\n"


async def _yes(task):
    return True


async def _no(task):
    return False


def test_auto_mode_lists_everything_but_runs_only_safe_targets(app_for):
    app = app_for(AUTO_MAKEFILE)

    assert {task.name: task.runnable for task in app.list_tasks()} == {
        "deploy": False,
        "test": True,
    }
    assert asyncio.run(app.run_task("test")).status == "passed"
    with pytest.raises(TaskNotRunnable, match="govern 'deploy'"):
        asyncio.run(app.run_task("deploy"))
    assert [tool.name for tool in build_direct_tools(app)] == ["make_test"]


def test_legacy_auto_run_restores_running_every_target(repo):
    app = build_application(repo(AUTO_MAKEFILE), legacy_auto_run=True)

    assert asyncio.run(app.run_task("deploy")).status == "passed"


def test_dangerous_task_requires_approval(app_for):
    app = app_for(DEPLOY_MAKEFILE, DANGEROUS)

    with pytest.raises(ApprovalRequired, match="unavailable"):
        asyncio.run(app.run_task("deploy"))
    with pytest.raises(ApprovalRequired, match="denied"):
        asyncio.run(app.run_task("deploy", approve=_no))
    assert asyncio.run(app.run_task("deploy", approve=_yes)).status == "passed"


def test_require_approval_is_configurable(app_for):
    app = app_for(
        ".PHONY: build\nbuild:\n\t@true\n",
        "schema_version: 1\ndefaults:\n  require_approval: [write]\ntasks:\n  build:\n"
        "    risk: write\n",
    )

    with pytest.raises(ApprovalRequired):
        asyncio.run(app.run_task("build"))
