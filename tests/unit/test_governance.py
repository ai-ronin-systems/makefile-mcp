import asyncio

import pytest

from makefile_mcp.app import build_application
from makefile_mcp.errors import TaskNotRunnable
from makefile_mcp.mcp.presentation import build_direct_tools

AUTO_MAKEFILE = ".PHONY: test deploy\ntest:\n\t@echo testing\ndeploy:\n\t@echo deploying\n"


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
