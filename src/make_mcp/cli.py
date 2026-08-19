"""Typer CLI. All task policy and execution remain in the application/core modules."""

import asyncio
import json
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel

from make_mcp.app import Application, build_application
from make_mcp.errors import MakeMcpError

cli = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Safely expose selected Make targets over CLI and MCP.",
)


class State:
    root: Path | None = None
    application: Application | None = None


state = State()


def _app() -> Application:
    if state.application is None:
        state.application = build_application(state.root)
    return state.application


def _data(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_data(item) for item in value]
    return value


def _json(value: Any) -> None:
    typer.echo(json.dumps(_data(value), indent=2, sort_keys=True))


def _fail(exc: MakeMcpError) -> None:
    typer.echo(f"error: {exc}", err=True)
    raise typer.Exit(code=2)


@cli.callback()
def callback(
    root: Annotated[
        Path | None,
        typer.Option("--root", help="Repository path; defaults to auto-detection."),
    ] = None,
) -> None:
    state.root = root
    state.application = None


@cli.command("list")
def list_command(
    context: Annotated[str, typer.Option("--context", "-c")] = "root",
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        tasks = _app().list_tasks(context)
    except MakeMcpError as exc:
        _fail(exc)
    if json_output:
        _json(tasks)
        return
    for task in tasks:
        description = f" — {task.description}" if task.description else ""
        typer.echo(f"{task.name:<24} [{task.risk}] {description}".rstrip())


@cli.command("describe")
def describe_command(
    task: str,
    context: Annotated[str, typer.Option("--context", "-c")] = "root",
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        definition = _app().describe_task(task, context)
    except MakeMcpError as exc:
        _fail(exc)
    if json_output:
        _json(definition)
        return
    typer.echo(f"Task: {definition.name}")
    typer.echo(f"Context: {definition.context}")
    typer.echo(f"Risk: {definition.risk}")
    typer.echo(f"Exposure: {definition.exposure_source}")
    typer.echo(f"Timeout: {definition.timeout_seconds}s")
    if definition.description:
        typer.echo(f"Description: {definition.description}")
    if definition.variables:
        typer.echo("Variables:")
        for name, spec in definition.variables.items():
            marker = "required" if spec.required else "optional"
            typer.echo(f"  {name}: {spec.type} ({marker})")


@cli.command("run")
def run_command(
    task: str,
    assignments: Annotated[
        list[str] | None,
        typer.Argument(help="Declared KEY=VALUE task variables."),
    ] = None,
    context: Annotated[str, typer.Option("--context", "-c")] = "root",
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    variables: dict[str, str] = {}
    for item in assignments or []:
        if "=" not in item:
            typer.echo(f"error: variable must use KEY=VALUE syntax: {item}", err=True)
            raise typer.Exit(code=2)
        key, value = item.split("=", 1)
        if key in variables:
            typer.echo(f"error: duplicate variable: {key}", err=True)
            raise typer.Exit(code=2)
        variables[key] = value
    try:
        result = asyncio.run(_app().run_task(task, variables, context))
    except MakeMcpError as exc:
        _fail(exc)
    if json_output:
        _json(result)
    else:
        typer.echo(f"{result.task}: {result.status} ({result.duration_ms} ms)")
        if result.stdout:
            typer.echo(result.stdout, nl=not result.stdout.endswith("\n"))
        if result.stderr:
            typer.echo(result.stderr, err=True, nl=not result.stderr.endswith("\n"))
        if result.truncated:
            typer.echo("[output truncated]", err=True)
    if result.status != "passed":
        raise typer.Exit(code=1)


@cli.command("doctor")
def doctor_command(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    try:
        result = _app().doctor()
    except MakeMcpError as exc:
        _fail(exc)
    if json_output:
        _json(result)
    else:
        typer.echo("doctor: ok" if result.ok else "doctor: problems found")
        for finding in result.findings:
            scope = "/".join(part for part in [finding.context, finding.task] if part)
            suffix = f" ({scope})" if scope else ""
            typer.echo(f"[{finding.severity}] {finding.code}{suffix}: {finding.message}")
    if not result.ok:
        raise typer.Exit(code=1)


@cli.command("serve")
def serve_command() -> None:
    from make_mcp.mcp_server import run_stdio_server

    run_stdio_server(_app())


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
