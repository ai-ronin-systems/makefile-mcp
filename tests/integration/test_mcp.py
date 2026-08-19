import pytest

pytest.importorskip("mcp")
from mcp import Client

from make_mcp.mcp.presentation import McpPresentation
from make_mcp.mcp.server import create_server


@pytest.mark.asyncio
async def test_generic_mode_lists_and_calls_only_governed_tasks(app_for):
    app = app_for(
        ".PHONY: hello hidden\n"
        "hello: ## Hello\n\t@echo hello\n"
        "hidden: ## Documentation is not authorization\n\t@true\n",
        "schema_version: 1\ntasks:\n  hello: {}\ncapabilities:\n  fixture.hello: hello\n",
    )
    server = create_server(app, McpPresentation.GENERIC)
    async with Client(server) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}
        assert names == {"list_tasks", "describe_task", "run_task"}

        listed = await client.call_tool("list_tasks", {"context": "root"})
        assert listed.structured_content["ok"] is True
        data = listed.structured_content["data"]
        assert data["exposure_mode"] == "governed"
        assert [task["name"] for task in data["tasks"]] == ["hello"]
        assert data["capabilities"] == {"fixture.hello": "hello"}

        ran = await client.call_tool("run_task", {"task": "hello", "context": "root"})
        assert ran.structured_content["data"]["status"] == "passed"

        rejected = await client.call_tool("run_task", {"task": "hidden", "context": "root"})
        assert rejected.is_error is True
        assert rejected.structured_content is None


@pytest.mark.asyncio
async def test_direct_mode_registers_one_typed_tool_per_exposed_task(app_for):
    app = app_for(
        ".PHONY: deploy hidden\ndeploy:\n\t@echo $(ENV)\nhidden:\n\t@true\n",
        "schema_version: 1\n"
        "tasks:\n"
        "  deploy:\n"
        "    variables:\n"
        "      ENV:\n"
        "        type: enum\n"
        "        values: [staging, production]\n"
        "        required: true\n",
    )
    server = create_server(app, McpPresentation.DIRECT)
    async with Client(server) as client:
        tools = await client.list_tools()
        assert [tool.name for tool in tools.tools] == ["make_deploy"]
        schema = tools.tools[0].input_schema
        assert schema["properties"]["ENV"]["enum"] == ["staging", "production"]
        assert schema["required"] == ["ENV"]

        ran = await client.call_tool("make_deploy", {"ENV": "staging"})
        assert ran.structured_content["ok"] is True
        assert ran.structured_content["data"]["status"] == "passed"


@pytest.mark.asyncio
async def test_both_mode_exposes_generic_and_direct_tools(app_for):
    app = app_for("test:\n\t@true\n")
    server = create_server(app, McpPresentation.BOTH)
    async with Client(server) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
        assert names == {"list_tasks", "describe_task", "run_task", "make_test"}


@pytest.mark.asyncio
async def test_generic_run_reports_execution_failure_as_mcp_tool_error(app_for):
    app = app_for(
        ".PHONY: fail\nfail:\n\t@echo expected-failure >&2; exit 7\n",
        "schema_version: 1\ntasks:\n  fail: {}\n",
    )
    server = create_server(app, McpPresentation.GENERIC)
    async with Client(server) as client:
        failed = await client.call_tool("run_task", {"task": "fail", "context": "root"})
        assert failed.is_error is True
        assert failed.structured_content is None


@pytest.mark.asyncio
async def test_direct_run_reports_execution_failure_as_mcp_tool_error(app_for):
    app = app_for(
        ".PHONY: fail\nfail:\n\t@exit 9\n",
        "schema_version: 1\ntasks:\n  fail: {}\n",
    )
    server = create_server(app, McpPresentation.DIRECT)
    async with Client(server) as client:
        failed = await client.call_tool("make_fail", {})
        assert failed.is_error is True
        assert failed.structured_content is None


@pytest.mark.asyncio
async def test_generic_validation_failure_is_mcp_tool_error(app_for):
    app = app_for(
        ".PHONY: hello\nhello:\n\t@true\n",
        "schema_version: 1\ntasks:\n  hello: {}\n",
    )
    server = create_server(app, McpPresentation.GENERIC)
    async with Client(server) as client:
        rejected = await client.call_tool(
            "run_task",
            {"task": "hello", "context": "root", "variables": {"NOPE": "x"}},
        )
        assert rejected.is_error is True
        assert rejected.structured_content is None


@pytest.mark.asyncio
async def test_generic_preview_reports_start_and_completion_progress(app_for):
    app = app_for(
        ".PHONY: write\nwrite:\n\t@touch preview-marker\n",
        "schema_version: 1\ntasks:\n  write: {}\n",
    )
    server = create_server(app, McpPresentation.GENERIC)
    progress: list[tuple[float, float | None, str | None]] = []

    async def on_progress(value: float, total: float | None, message: str | None) -> None:
        progress.append((value, total, message))

    async with Client(server) as client:
        result = await client.call_tool(
            "run_task",
            {"task": "write", "preview": True},
            progress_callback=on_progress,
        )

    assert result.structured_content["data"]["preview"] is True
    assert not (app.root / "preview-marker").exists()
    assert progress == [
        (0.0, 1.0, "Starting preview: write"),
        (1.0, 1.0, "Completed preview: write"),
    ]


@pytest.mark.asyncio
async def test_direct_tool_schema_has_preview_and_reports_progress(app_for):
    app = app_for(".PHONY: test\ntest:\n\t@true\n")
    server = create_server(app, McpPresentation.DIRECT)
    progress: list[tuple[float, float | None, str | None]] = []

    async def on_progress(value: float, total: float | None, message: str | None) -> None:
        progress.append((value, total, message))

    async with Client(server) as client:
        tool = (await client.list_tools()).tools[0]
        assert tool.input_schema["properties"]["preview"]["type"] == "boolean"
        result = await client.call_tool("make_test", {}, progress_callback=on_progress)

    assert result.structured_content["data"]["preview"] is False
    assert progress == [
        (0.0, 1.0, "Starting run: test"),
        (1.0, 1.0, "Completed run: test"),
    ]
