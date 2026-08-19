import pytest

pytest.importorskip("mcp")
from mcp import Client

from make_mcp.mcp_server import create_server


@pytest.mark.asyncio
async def test_mcp_lists_and_calls_tools(app_for):
    app = app_for(".PHONY: hello\nhello: ## Hello\n\t@echo hello\n")
    server = create_server(app)
    async with Client(server) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}
        assert names == {"list_tasks", "describe_task", "run_task"}
        listed = await client.call_tool("list_tasks", {"context": "root"})
        assert listed.structured_content["ok"] is True
        ran = await client.call_tool("run_task", {"task": "hello", "context": "root"})
        assert ran.structured_content["data"]["status"] == "passed"
