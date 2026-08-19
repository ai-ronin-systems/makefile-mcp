"""Derive direct per-task MCP tools without depending on the MCP SDK.

Keeping schema/name derivation SDK-independent makes the presentation layer easy to test and
ensures direct tools remain thin delegates to the protocol-agnostic application facade.
"""

import hashlib
import inspect
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from makefile_mcp.app import Application
from makefile_mcp.models import TaskDefinition, TaskResult, TaskStatus, VariableSpec, VariableType
from makefile_mcp.syntax import SAFE_LITERAL_PATTERN, SAFE_PATH_PATTERN, parse_boolean_literal

_TOOL_COMPONENT = re.compile(r"[^A-Za-z0-9_.-]+")
_MAX_TOOL_NAME = 128


_MAX_MCP_ERROR_DIAGNOSTIC_BYTES = 8192
_MCP_DIAGNOSTIC_TRUNCATED = "\n[MCP diagnostic truncated]"
_EXECUTOR_OUTPUT_TRUNCATED = "[task output truncated by executor]"


def _bounded_utf8(text: str, *, max_bytes: int) -> str:
    """Return text bounded by encoded UTF-8 bytes without splitting a code point."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text

    marker = _MCP_DIAGNOSTIC_TRUNCATED.encode("utf-8")
    budget = max(0, max_bytes - len(marker))
    prefix = encoded[:budget].decode("utf-8", errors="ignore")
    return prefix + _MCP_DIAGNOSTIC_TRUNCATED


class McpPresentation(StrEnum):
    """How the same authorized catalog is presented to an MCP client."""

    GENERIC = "generic"
    DIRECT = "direct"
    BOTH = "both"


@dataclass(frozen=True)
class DirectTool:
    """SDK-independent description of one generated direct MCP tool."""

    name: str
    title: str
    description: str
    task: TaskDefinition
    fn: Any


def response_success(data: Any) -> dict[str, Any]:
    """Normalize application models into the stable MCP success envelope."""
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    elif isinstance(data, list):
        data = [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item for item in data
        ]
    return {"ok": True, "data": data}


def task_response(result: TaskResult) -> dict[str, Any]:
    """Return a successful task result or raise so MCP sets ``isError=true``.

    The protocol-level application keeps TaskResult for CLI/embedding callers. The MCP adapter
    maps non-passing execution outcomes to ordinary Python exceptions because MCPServer converts
    those into model-visible tool errors. Do not return an ``ok: false`` payload: MCP clients
    would treat that as a successful tool call.
    """
    if result.status == TaskStatus.PASSED:
        return response_success(result)

    streams: list[str] = []
    if result.truncated:
        # Put this first so a second MCP-specific truncation cannot hide that the executor's
        # retained stdout/stderr was already incomplete.
        streams.append(_EXECUTOR_OUTPUT_TRUNCATED)
    if result.stdout.strip():
        streams.append(f"stdout:\n{result.stdout.strip()}")
    if result.stderr.strip():
        streams.append(f"stderr:\n{result.stderr.strip()}")
    details = "\n\n".join(streams)
    summary = (
        f"Make target {result.task!r} in context {result.context!r} "
        f"ended with status {result.status.value!r}"
    )
    if result.exit_code is not None:
        summary += f" (exit code {result.exit_code})"
    if details:
        summary += f":\n{details}"

    # Tool errors are model-visible text rather than structured output. Bound the complete
    # diagnostic, including caller-visible task/context identity, so an unusually long trusted
    # target or context cannot bypass the documented 8 KiB protocol budget. Full bounded task
    # output remains available to CLI/embedding callers.
    raise RuntimeError(_bounded_utf8(summary, max_bytes=_MAX_MCP_ERROR_DIAGNOSTIC_BYTES))


def _slug(value: str) -> str:
    """Map context/target names to MCP-recommended tool-name characters."""
    slug = _TOOL_COMPONENT.sub("_", value).strip("._-")
    return slug or "task"


def _short_hash(context: str, target: str) -> str:
    """Return a stable short identity suffix for rare direct-tool name collisions."""
    payload = f"{context}\0{target}".encode()
    return hashlib.sha256(payload).hexdigest()[:8]


def direct_tool_base_name(task: TaskDefinition) -> str:
    """Create an agent-readable direct tool name before collision resolution."""
    target = _slug(task.name)
    name = f"make_{target}" if task.context == "root" else f"make_{_slug(task.context)}_{target}"

    # MCP tool names are capped at 128 characters. Preserve the readable prefix and append
    # stable identity only when truncation is necessary.
    if len(name) > _MAX_TOOL_NAME:
        suffix = _short_hash(task.context, task.name)
        name = f"{name[: _MAX_TOOL_NAME - len(suffix) - 1]}_{suffix}"
    return name


def _name_with_suffix(base: str, suffix: str) -> str:
    """Append one identity suffix while preserving the MCP 128-character name limit."""
    return f"{base[: _MAX_TOOL_NAME - len(suffix) - 1]}_{suffix}"


def _unique_tool_name(task: TaskDefinition, used: set[str]) -> str:
    """Resolve slug/hash collisions deterministically without duplicate MCP tool names."""
    base = direct_tool_base_name(task)
    if base not in used:
        return base

    digest = hashlib.sha256(f"{task.context}\0{task.name}".encode()).hexdigest()
    # Eight hex characters keep normal collision names readable. If two distinct identities
    # collide on that prefix, extend the same stable digest until the candidate is unique.
    for width in range(8, len(digest) + 1, 4):
        candidate = _name_with_suffix(base, digest[:width])
        if candidate not in used:
            return candidate
    raise RuntimeError("could not derive a unique direct MCP tool name")


def _annotation(spec: VariableSpec) -> Any:
    """Map a governed input contract to an MCP/Pydantic-friendly Python annotation."""
    field_options: dict[str, Any] = {}
    if spec.description:
        field_options["description"] = spec.description

    if spec.type == VariableType.INTEGER:
        annotation: Any = int
    elif spec.type == VariableType.BOOLEAN:
        annotation = bool
    elif spec.type == VariableType.ENUM:
        # Literal[...] exposes the exact enum choices in the generated JSON Schema.
        # This is intentionally constructed at runtime from governed configuration. getattr is
        # deliberate here: static type checkers treat Literal as a special form rather than a
        # normal runtime-subscriptable object.
        literal_getitem = getattr(Literal, "__getitem__")  # noqa: B009
        annotation = literal_getitem(tuple(spec.values))
    else:
        # Runtime validation remains authoritative, but expose the lexical Make-safe grammar to
        # MCP clients when JSON Schema can represent it. Repository confinement for PATH still
        # happens only at execution time after resolving against the selected context.
        annotation = str
        if spec.type == VariableType.TOKEN:
            field_options["pattern"] = SAFE_LITERAL_PATTERN.pattern
        elif spec.type == VariableType.PATH:
            field_options["pattern"] = SAFE_PATH_PATTERN.pattern

    if field_options:
        annotation = Annotated[annotation, Field(**field_options)]
    return annotation


def _typed_default(spec: VariableSpec) -> Any:
    """Render a configured default using the type shown in the direct MCP schema."""
    raw = spec.default
    if raw is None:
        return None
    if spec.type == VariableType.INTEGER:
        return int(str(raw), 10)
    if spec.type == VariableType.BOOLEAN:
        return parse_boolean_literal(str(raw))
    return str(raw)


def _signature(task: TaskDefinition) -> inspect.Signature:
    """Build the direct-tool signature from an already-validated task contract."""
    parameters: list[inspect.Parameter] = []
    for name, spec in task.variables.items():
        if spec.default is not None:
            default = _typed_default(spec)
        elif spec.required:
            default = inspect.Parameter.empty
        else:
            # None means "argument omitted" and is stripped before Application.run_task().
            default = None
        parameters.append(
            inspect.Parameter(
                name=name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=_annotation(spec),
            )
        )
    parameters.append(
        inspect.Parameter(
            "preview",
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=False,
            annotation=bool,
        )
    )
    return inspect.Signature(parameters, return_annotation=dict[str, Any])


def _wire_variables(arguments: dict[str, Any]) -> dict[str, str]:
    """Convert MCP scalar values back to the executor's text input contract."""
    variables: dict[str, str] = {}
    for name, value in arguments.items():
        if value is None:
            continue
        if isinstance(value, bool):
            variables[name] = "true" if value else "false"
        else:
            variables[name] = str(value)
    return variables


def _direct_callable(app: Application, task: TaskDefinition, tool_name: str) -> Any:
    """Create one thin direct tool that delegates to ``Application.run_task``."""

    async def run_direct(**kwargs: Any) -> dict[str, Any]:
        preview = bool(kwargs.pop("preview", False))
        return task_response(
            await app.run_task(
                task.name,
                _wire_variables(kwargs),
                task.context,
                preview=preview,
            )
        )

    # MCP SDK v2 derives inputSchema from inspect.signature(). A custom signature exposes the
    # configured task variables without source generation or a parallel validation path.
    run_direct.__name__ = tool_name
    run_direct.__qualname__ = tool_name
    run_direct.__doc__ = task.description or (
        f"Run Make target {task.name!r} in context {task.context!r}."
    )
    run_direct.__signature__ = _signature(task)  # type: ignore[attr-defined]
    return run_direct


def build_direct_tools(app: Application) -> list[DirectTool]:
    """Snapshot the authorized catalog into one generated MCP tool per task/context pair."""
    result: list[DirectTool] = []
    used: set[str] = set()
    for context in app.list_contexts():
        for task in app.list_tasks(context):
            name = _unique_tool_name(task, used)
            used.add(name)
            label = task.name if task.context == "root" else f"{task.context}:{task.name}"
            result.append(
                DirectTool(
                    name=name,
                    title=f"Make {label}",
                    description=task.description
                    or f"Run Make target {task.name!r} in context {task.context!r}.",
                    task=task,
                    fn=_direct_callable(app, task, name),
                )
            )
    return result
