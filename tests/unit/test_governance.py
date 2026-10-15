import asyncio
import json

import pytest
from mcp import Client, types

from makefile_mcp.app import build_application
from makefile_mcp.errors import ApprovalRequired, TaskNotRunnable
from makefile_mcp.mcp.presentation import McpPresentation, build_direct_tools
from makefile_mcp.mcp.server import create_server

AUTO_MAKEFILE = ".PHONY: test deploy\ntest:\n\t@echo testing\ndeploy:\n\t@echo deploying\n"

DANGEROUS = (
    "schema_version: 1\n"
    "audit:\n"
    "  path: logs/audit.jsonl\n"
    "tasks:\n"
    "  deploy:\n"
    "    risk: dangerous\n"
    "    variables:\n"
    "      TOKEN:\n"
    "        type: string\n"
    "        secret: true\n"
)
DEPLOY_MAKEFILE = ".PHONY: deploy\ndeploy:\n\t@cat $(MAKEFILE_MCP_INPUT)\n"


async def _yes(task):
    return True


async def _no(task):
    return False


def _audit(root):
    lines = (root / "logs/audit.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


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


def test_dangerous_task_requires_approval_and_is_audited(app_for, tmp_path):
    app = app_for(DEPLOY_MAKEFILE, DANGEROUS)

    with pytest.raises(ApprovalRequired, match="unavailable"):
        asyncio.run(app.run_task("deploy", {"TOKEN": "s3cr3t"}))
    with pytest.raises(ApprovalRequired, match="denied"):
        asyncio.run(app.run_task("deploy", {"TOKEN": "s3cr3t"}, approve=_no))
    result = asyncio.run(app.run_task("deploy", {"TOKEN": "s3cr3t"}, approve=_yes))
    assert result.status == "passed"

    records = _audit(tmp_path)
    assert [r["approval"] for r in records] == ["unavailable", "denied", "approved"]
    assert [r["status"] for r in records] == ["refused", "refused", "passed"]
    assert records[-1]["arguments"] == {"TOKEN": "***"}
    assert records[-1]["risk"] == "dangerous"
    assert records[-1]["output_bytes"] > 0
    assert "s3cr3t" not in (tmp_path / "logs/audit.jsonl").read_text(encoding="utf-8")


def test_require_approval_is_configurable(app_for):
    app = app_for(
        ".PHONY: build\nbuild:\n\t@true\n",
        "schema_version: 1\ndefaults:\n  require_approval: [write]\ntasks:\n  build:\n"
        "    risk: write\n",
    )

    with pytest.raises(ApprovalRequired):
        asyncio.run(app.run_task("build"))


def test_secret_variables_cannot_have_defaults(app_for):
    from makefile_mcp.errors import ConfigurationError

    with pytest.raises(ConfigurationError, match="secret"):
        app_for(
            ".PHONY: x\nx:\n\t@true\n",
            "schema_version: 1\ntasks:\n  x:\n    variables:\n"
            "      K:\n        type: string\n        secret: true\n        default: d\n",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("answer", [True, False])
async def test_mcp_asks_the_human_through_elicitation(app_for, answer, mode):
    app = app_for(DEPLOY_MAKEFILE, DANGEROUS)
    prompts = []

    async def elicit(context, params):
        prompts.append(params.message)
        return types.ElicitResult(action="accept", content={"approve": answer})

    async with Client(
        create_server(app, McpPresentation.BOTH), elicitation_callback=elicit, mode=mode
    ) as client:
        tools = await client.list_tools()
        assert all("approval" not in tool.input_schema["properties"] for tool in tools.tools)
        generic = await client.call_tool("run_task", {"task": "deploy"})
        direct = await client.call_tool("make_deploy", {})

    assert prompts == ["Approve dangerous Make target 'deploy'?"] * 2
    assert generic.is_error is not answer
    assert direct.is_error is not answer


@pytest.mark.asyncio
async def test_mcp_refuses_when_client_cannot_elicit(app_for):
    app = app_for(DEPLOY_MAKEFILE, DANGEROUS)

    async with Client(create_server(app, McpPresentation.GENERIC)) as client:
        result = await client.call_tool("run_task", {"task": "deploy"})

    assert result.is_error is True
    assert "approval" in result.content[0].text
