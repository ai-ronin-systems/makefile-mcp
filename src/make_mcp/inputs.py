"""Validate task inputs and keep arbitrary strings outside GNU Make syntax."""

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from make_mcp.errors import VariableValidationError
from make_mcp.filesystem import ensure_within_root
from make_mcp.models import TaskDefinition, VariableSpec, VariableType
from make_mcp.syntax import (
    RESERVED_MAKE_VARIABLES,
    SAFE_LITERAL_PATTERN,
    SAFE_PATH_PATTERN,
    is_task_variable_name,
    parse_boolean_literal,
)


def _json_utf8_bytes(value: object, *, label: str) -> bytes:
    """Serialize JSON data and normalize invalid Unicode at the caller/config boundary."""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise VariableValidationError(
            f"{label} contains text that cannot be encoded as valid UTF-8"
        ) from exc


def _safe_literal(raw: str, *, kind: str) -> str:
    """Validate values that are safe to transport as GNU Make `NAME=value` assignments."""
    if not SAFE_LITERAL_PATTERN.fullmatch(raw):
        raise VariableValidationError(
            f"unsafe {kind} value {raw!r}; allowed characters are letters, digits, . _ / @ : + -"
        )
    return raw


def _convert_variable(spec: VariableSpec, raw: str, *, root: Path, cwd: Path) -> str:
    """Normalize one declared input according to its type-specific transport contract."""
    if spec.type == VariableType.STRING:
        # Arbitrary strings are data, not Make syntax. They are serialized to the private
        # JSON side-channel by `string_input_file`; no character filtering belongs here.
        return raw
    if spec.type == VariableType.TOKEN:
        return _safe_literal(raw, kind="token")
    if spec.type == VariableType.INTEGER:
        try:
            return str(int(raw, 10))
        except ValueError as exc:
            raise VariableValidationError(f"expected integer, got {raw!r}") from exc
    if spec.type == VariableType.BOOLEAN:
        try:
            return "true" if parse_boolean_literal(raw) else "false"
        except ValueError as exc:
            raise VariableValidationError(str(exc)) from exc
    if spec.type == VariableType.ENUM:
        if raw not in spec.values:
            raise VariableValidationError(f"expected one of {spec.values}, got {raw!r}")
        return _safe_literal(raw, kind="enum")
    if spec.type == VariableType.PATH:
        if not SAFE_PATH_PATTERN.fullmatch(raw):
            raise VariableValidationError(
                f"unsafe path value {raw!r}; allowed characters are letters, digits, . _ / @ : + -"
            )
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = cwd / candidate
        resolved = str(ensure_within_root(root, candidate, must_exist=False))
        if not SAFE_PATH_PATTERN.fullmatch(resolved):
            raise VariableValidationError(
                "resolved repository path contains characters unsafe for Make variable transport"
            )
        return resolved
    raise VariableValidationError(f"unsupported variable type: {spec.type}")


def validate_variables(
    task: TaskDefinition,
    supplied: dict[str, str],
    *,
    root: Path,
    cwd: Path,
    input_limit_bytes: int = 1_048_576,
) -> dict[str, str]:
    """Reject undeclared inputs and normalize every declared value before transport."""
    # The application facade is a runtime boundary too: Python annotations do not enforce
    # caller types. Reject malformed mappings before JSON encoding, sorting, regex matching,
    # or path conversion can leak TypeError/AttributeError to an embedding caller.
    if not isinstance(supplied, dict):
        raise VariableValidationError("caller variables must be a mapping")
    if any(not isinstance(name, str) for name in supplied):
        raise VariableValidationError("caller variable names must be strings")
    if any(not isinstance(value, str) for value in supplied.values()):
        raise VariableValidationError("caller variable values must be strings")

    # Bound the complete caller-controlled mapping before per-type parsing. This prevents huge
    # token/path/unknown values from reaching path resolution or the OS argv boundary.
    encoded = _json_utf8_bytes(supplied, label="caller input")
    if len(encoded) > input_limit_bytes:
        raise VariableValidationError(f"caller input exceeds limit of {input_limit_bytes} bytes")

    unknown = sorted(set(supplied) - set(task.variables))
    if unknown:
        raise VariableValidationError(f"undeclared variables: {', '.join(unknown)}")

    result: dict[str, str] = {}
    for name, spec in task.variables.items():
        # Config validation already enforces this. Keeping the check at the input boundary
        # makes TaskDefinition safe even when a test/integration constructs it directly.
        if not is_task_variable_name(name):
            raise VariableValidationError(f"invalid declared variable name: {name}")
        if name in RESERVED_MAKE_VARIABLES:
            raise VariableValidationError(f"reserved declared variable name: {name}")
        if name in supplied:
            result[name] = _convert_variable(spec, supplied[name], root=root, cwd=cwd)
        elif spec.default is not None:
            result[name] = _convert_variable(spec, str(spec.default), root=root, cwd=cwd)
        elif spec.required:
            raise VariableValidationError(f"missing required variable: {name}")
    return result


def make_variables(task: TaskDefinition, validated: dict[str, str]) -> dict[str, str]:
    """Return only inputs whose normalized grammar is safe for GNU Make assignments."""
    return {
        name: value
        for name, value in validated.items()
        if task.variables[name].type != VariableType.STRING
    }


def _string_variables(task: TaskDefinition, validated: dict[str, str]) -> dict[str, str]:
    """Return arbitrary string data that must never be interpolated into GNU Make syntax."""
    return {
        name: value
        for name, value in validated.items()
        if task.variables[name].type == VariableType.STRING
    }


def _task_has_string_variables(task: TaskDefinition) -> bool:
    # Create the JSON file even when all string inputs are optional and omitted. This gives
    # recipes one stable contract: declaring `string` always means MAKE_MCP_INPUT exists.
    return any(spec.type == VariableType.STRING for spec in task.variables.values())


@contextmanager
def string_input_file(
    task: TaskDefinition,
    validated: dict[str, str],
    *,
    input_limit_bytes: int,
) -> Iterator[Path | None]:
    """Create and destroy the private per-invocation JSON payload for string inputs."""
    if not _task_has_string_variables(task):
        yield None
        return

    # V1 is POSIX-only. Pinning the base to /tmp avoids inheriting a caller-controlled TMPDIR
    # whose pathname could itself contain Make syntax. TemporaryDirectory is mode 0700.
    with tempfile.TemporaryDirectory(prefix="make-mcp-", dir="/tmp") as temporary_directory:
        payload_path = Path(temporary_directory) / "input.json"

        # JSON is the data boundary. Arbitrary bytes are encoded as data and never become a
        # Make assignment, environment value, shell source fragment, or generated recipe.
        # Check the actual UTF-8 JSON representation so quotes/backslashes/control-character
        # escaping cannot make the on-disk payload larger than the configured caller bound.
        payload = _json_utf8_bytes(
            _string_variables(task, validated),
            label="string input payload",
        )
        if len(payload) > input_limit_bytes:
            raise VariableValidationError(
                f"string input payload exceeds limit of {input_limit_bytes} bytes"
            )
        payload_path.write_bytes(payload)
        payload_path.chmod(0o600)
        yield payload_path
        # TemporaryDirectory removes both file and private directory on normal/error/cancel
        # paths once the recipe/process lifecycle has finished. Do not persist secrets here.
