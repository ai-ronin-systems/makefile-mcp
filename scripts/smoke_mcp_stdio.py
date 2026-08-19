#!/usr/bin/env python3
"""Smoke-test the installed Makefile MCP console script through a real MCP stdio subprocess."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client


async def _smoke() -> None:
    with tempfile.TemporaryDirectory(prefix="makefile-mcp-smoke-") as tmp:
        root = Path(tmp)
        (root / "Makefile").write_text(
            ".PHONY: hello\nhello: ## Package MCP smoke\n\t@echo mcp-smoke-ok\n",
            encoding="utf-8",
        )
        server = StdioServerParameters(
            command="makefile-mcp",
            args=["--root", str(root), "serve", "--tools", "generic"],
            cwd=root,
        )
        async with Client(stdio_client(server)) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools.tools}
            assert names == {"list_tasks", "describe_task", "run_task"}, names

            result = await client.call_tool(
                "run_task",
                {"task": "hello", "context": "root"},
            )
            assert result.is_error is False
            assert result.structured_content is not None
            data = result.structured_content["data"]
            assert data["status"] == "passed", data
            assert "mcp-smoke-ok" in data["stdout"], data


def main() -> None:
    asyncio.run(asyncio.wait_for(_smoke(), timeout=30))


if __name__ == "__main__":
    main()
