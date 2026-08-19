"""Thin MCP v2 SDK adapter with generic, direct, and combined presentations."""

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from makefile_mcp.app import Application, build_application
from makefile_mcp.mcp.presentation import (
    DirectTool,
    McpPresentation,
    build_direct_tools,
    response_success,
    task_response,
)
from makefile_mcp.version import __version__

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
EXECUTE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=True,
)


async def _run_with_progress(
    ctx: Context,
    label: str,
    operation: Callable[[], Awaitable[dict[str, Any]]],
    *,
    preview: bool,
) -> dict[str, Any]:
    """Report truthful start/completion feedback without inventing in-task percentages."""
    mode = "preview" if preview else "run"
    await ctx.report_progress(0.0, 1.0, f"Starting {mode}: {label}")
    try:
        result = await operation()
    except Exception:
        await ctx.report_progress(1.0, 1.0, f"Failed {mode}: {label}")
        raise
    await ctx.report_progress(1.0, 1.0, f"Completed {mode}: {label}")
    return result


def _progress_direct_callable(direct: DirectTool) -> Any:
    """Wrap one generated direct tool with MCP Context progress, preserving its schema."""

    async def run_direct_with_progress(ctx: Context, **kwargs: Any) -> dict[str, Any]:
        preview = bool(kwargs.get("preview", False))
        label = direct.task.name
        if direct.task.context != "root":
            label = f"{direct.task.context}:{label}"
        return await _run_with_progress(
            ctx,
            label,
            lambda: direct.fn(**kwargs),
            preview=preview,
        )

    parameters = list(inspect.signature(direct.fn).parameters.values())
    parameters.append(
        inspect.Parameter(
            "ctx",
            kind=inspect.Parameter.KEYWORD_ONLY,
            annotation=Context,
        )
    )
    run_direct_with_progress.__name__ = direct.name
    run_direct_with_progress.__qualname__ = direct.name
    run_direct_with_progress.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        parameters,
        return_annotation=dict[str, Any],
    )
    return run_direct_with_progress


async def _generic_task_call(
    app: Application,
    task: str,
    variables: dict[str, str],
    context: str,
    preview: bool,
) -> dict[str, Any]:
    return task_response(await app.run_task(task, variables, context, preview=preview))


def _register_generic_tools(server: MCPServer, app: Application) -> None:
    """Register the stable list/describe/run API over the authorized catalog."""

    async def list_tasks(context: str = "root") -> dict[str, Any]:
        """List callable Make targets and semantic capability mappings."""
        return response_success(
            {
                "exposure_mode": "governed" if app.governed else "auto",
                "tasks": [task.model_dump(mode="json") for task in app.list_tasks(context)],
                # Capabilities are context-scoped views of the same authorized catalog;
                # never advertise a mapping whose target cannot run in this context.
                "capabilities": app.list_capabilities(context),
            }
        )

    async def describe_task(task: str, context: str = "root") -> dict[str, Any]:
        """Describe a callable Make target, variables, risk, and timeout."""
        return response_success(app.describe_task(task, context))

    async def run_task(
        task: str,
        ctx: Context,
        variables: dict[str, str] | None = None,
        context: str = "root",
        preview: bool = False,
    ) -> dict[str, Any]:
        """Run or preview one callable Make target through the common execution path."""
        label = task if context == "root" else f"{context}:{task}"
        return await _run_with_progress(
            ctx,
            label,
            lambda: _generic_task_call(app, task, variables or {}, context, preview),
            preview=preview,
        )

    server.add_tool(
        list_tasks,
        name="list_tasks",
        title="List Make tasks",
        annotations=READ_ONLY,
        structured_output=True,
    )
    server.add_tool(
        describe_task,
        name="describe_task",
        title="Describe a Make task",
        annotations=READ_ONLY,
        structured_output=True,
    )
    server.add_tool(
        run_task,
        name="run_task",
        title="Run a Make task",
        annotations=EXECUTE,
        structured_output=True,
    )


def _register_direct_tools(server: MCPServer, app: Application) -> None:
    """Register a startup snapshot with one typed MCP tool per callable task/context."""
    for direct in build_direct_tools(app):
        server.add_tool(
            _progress_direct_callable(direct),
            name=direct.name,
            title=direct.title,
            description=direct.description,
            annotations=EXECUTE,
            structured_output=True,
        )


def create_server(
    app: Application,
    presentation: McpPresentation | str = McpPresentation.DIRECT,
) -> MCPServer:
    """Create one MCP server presentation over the shared catalog and executor."""
    presentation = McpPresentation(presentation)
    server = MCPServer(
        "makefile-mcp",
        description=(
            "Expose Make targets through auto-discovered or explicitly governed execution."
        ),
        version=__version__,
    )

    if presentation in {McpPresentation.GENERIC, McpPresentation.BOTH}:
        _register_generic_tools(server, app)
    if presentation in {McpPresentation.DIRECT, McpPresentation.BOTH}:
        _register_direct_tools(server, app)
    return server


def run_stdio_server(
    app: Application | None = None,
    *,
    presentation: McpPresentation | str = McpPresentation.DIRECT,
) -> None:
    """Run the configured MCP presentation over the built-in stdio transport."""
    create_server(app or build_application(), presentation=presentation).run(transport="stdio")


def main() -> None:
    """Run the default direct MCP stdio server."""
    run_stdio_server()


if __name__ == "__main__":
    main()
