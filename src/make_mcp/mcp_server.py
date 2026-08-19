"""Thin MCP v2 adapter: three tools, no Make policy or execution logic."""

from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel

from make_mcp.app import Application, build_application
from make_mcp.errors import MakeMcpError
from make_mcp.version import __version__

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
RUN_TASK = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=False,
)


def _success(data: Any) -> dict[str, Any]:
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    elif isinstance(data, list):
        data = [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for item in data
        ]
    return {"ok": True, "data": data}


def _expected_error(exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"type": type(exc).__name__, "message": str(exc)},
    }


def create_server(app: Application) -> MCPServer:
    server = MCPServer(
        "make-mcp",
        description="Expose explicitly allowed Make targets as structured tools.",
        version=__version__,
    )

    async def list_tasks(context: str = "root") -> dict[str, Any]:
        """List Make targets explicitly authorized for the selected context."""
        try:
            return _success(app.list_tasks(context))
        except MakeMcpError as exc:
            return _expected_error(exc)

    async def describe_task(task: str, context: str = "root") -> dict[str, Any]:
        """Describe an exposed Make target, variables, risk, and timeout."""
        try:
            return _success(app.describe_task(task, context))
        except MakeMcpError as exc:
            return _expected_error(exc)

    async def run_task(
        task: str,
        variables: dict[str, str] | None = None,
        context: str = "root",
    ) -> dict[str, Any]:
        """Run one already-exposed Make target with declared variables only."""
        try:
            return _success(await app.run_task(task, variables or {}, context))
        except MakeMcpError as exc:
            return _expected_error(exc)

    server.add_tool(
        list_tasks,
        name="list_tasks",
        title="List exposed Make tasks",
        annotations=READ_ONLY,
        structured_output=True,
    )
    server.add_tool(
        describe_task,
        name="describe_task",
        title="Describe an exposed Make task",
        annotations=READ_ONLY,
        structured_output=True,
    )
    server.add_tool(
        run_task,
        name="run_task",
        title="Run an exposed Make task",
        annotations=RUN_TASK,
        structured_output=True,
    )
    return server


def run_stdio_server(app: Application | None = None) -> None:
    create_server(app or build_application()).run(transport="stdio")


def main() -> None:
    run_stdio_server()


if __name__ == "__main__":
    main()
