"""Stable Make MCP data contracts and configuration models."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from make_mcp.syntax import (
    BOOLEAN_VALUES,
    CONTEXT_NAME_PATTERN,
    MCP_CONTROL_PARAMETER_NAMES,
    RESERVED_MAKE_VARIABLES,
    SAFE_LITERAL_PATTERN,
    SAFE_PATH_PATTERN,
    is_identifier_name,
    is_task_variable_name,
)


class StrictModel(BaseModel):
    """Base Pydantic contract that rejects unknown fields."""

    model_config = ConfigDict(extra="forbid")


class TaskRisk(StrEnum):
    """Advisory risk metadata associated with one callable task."""

    UNKNOWN = "unknown"
    SAFE = "safe"
    WRITE = "write"
    DANGEROUS = "dangerous"


class VariableType(StrEnum):
    """Supported governed input types and their transport classes."""

    TOKEN = "token"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ENUM = "enum"
    PATH = "path"
    # STRING is deliberately different from the other types: its value never becomes
    # Make syntax or a recipe argument. It is serialized into MAKE_MCP_INPUT JSON.
    STRING = "string"


class TaskStatus(StrEnum):
    """Normalized task execution outcomes returned by CLI and MCP."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"


class DoctorSeverity(StrEnum):
    """Severity level for one read-only doctor finding."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class VariableSpec(StrictModel):
    """One explicitly declared task input and its transport/validation contract."""

    type: VariableType = VariableType.TOKEN
    required: bool = False
    description: str | None = None
    values: list[str] = Field(default_factory=list)
    default: str | int | bool | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "VariableSpec":
        """Validate type-specific required/default and enum/default constraints."""
        if self.required and self.default is not None:
            raise ValueError("required variables cannot define a default")

        if self.type == VariableType.ENUM:
            if not self.values:
                raise ValueError("enum variables require non-empty values")
            unsafe = [value for value in self.values if not SAFE_LITERAL_PATTERN.fullmatch(value)]
            if unsafe:
                raise ValueError(
                    "enum values must use only Make-safe token characters: "
                    + ", ".join(repr(value) for value in unsafe)
                )
        elif self.values:
            raise ValueError("values is only valid for enum variables")

        if self.default is not None:
            raw = str(self.default)
            if self.type == VariableType.TOKEN and not SAFE_LITERAL_PATTERN.fullmatch(raw):
                raise ValueError(
                    "default token contains characters unsafe for Make variable transport"
                )
            if self.type == VariableType.PATH and not SAFE_PATH_PATTERN.fullmatch(raw):
                raise ValueError(
                    "default path contains characters unsafe for Make variable transport"
                )
            if self.type == VariableType.ENUM and raw not in self.values:
                raise ValueError("enum default must be one of values")
            if self.type == VariableType.INTEGER:
                try:
                    int(raw, 10)
                except ValueError as exc:
                    raise ValueError("integer default must be an integer") from exc
            if self.type == VariableType.BOOLEAN and raw.lower() not in BOOLEAN_VALUES:
                raise ValueError("boolean default must be a boolean value")
            # STRING defaults intentionally accept arbitrary text. They use the JSON
            # side-channel and therefore do not need Make/shell character filtering.
        return self


def _validate_task_variable_mapping(
    value: dict[str, "VariableSpec"],
) -> dict[str, "VariableSpec"]:
    """Validate task-input names once for both config and runtime task contracts."""
    invalid = [name for name in value if not is_task_variable_name(name)]
    if invalid:
        raise ValueError(
            "invalid task variable names (must be non-keyword Python identifiers): "
            + ", ".join(sorted(invalid))
        )
    control = sorted(set(value) & MCP_CONTROL_PARAMETER_NAMES)
    if control:
        raise ValueError(
            "task variable names reserved for JMIM tool controls cannot be exposed: "
            + ", ".join(control)
        )
    reserved = sorted(set(value) & RESERVED_MAKE_VARIABLES)
    if reserved:
        raise ValueError(
            "reserved GNU Make/Make MCP variables cannot be exposed: " + ", ".join(reserved)
        )
    return value


class TaskDefinition(StrictModel):
    """One callable target after discovery and exposure policy have been applied."""

    name: str
    description: str | None = None
    context: str = "root"
    risk: TaskRisk = TaskRisk.UNKNOWN
    timeout_seconds: int = Field(default=600, gt=0)
    variables: dict[str, VariableSpec] = Field(default_factory=dict)

    @field_validator("variables")
    @classmethod
    def valid_variable_names(cls, value: dict[str, VariableSpec]) -> dict[str, VariableSpec]:
        """Keep direct-constructed runtime tasks on the same input-name contract."""
        return _validate_task_variable_mapping(value)


@dataclass(frozen=True)
class ProjectContext:
    """Resolved repository directory associated with a named execution context."""

    directory: Path


class ProcessResult(StrictModel):
    """Bounded raw subprocess result before application status normalization."""

    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    truncated: bool = False
    started_at: datetime
    completed_at: datetime


class TaskResult(StrictModel):
    """Stable task result returned by CLI and MCP presentations."""

    task: str
    context: str
    status: TaskStatus
    exit_code: int | None = None
    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0)
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False
    preview: bool = False


class DoctorFinding(StrictModel):
    """One diagnostic observation produced by ``make-mcp doctor``."""

    code: str
    severity: DoctorSeverity
    message: str
    context: str | None = None
    task: str | None = None


class DoctorResult(StrictModel):
    """Aggregate result of a read-only repository diagnostic pass."""

    ok: bool
    findings: list[DoctorFinding] = Field(default_factory=list)


class DefaultsConfig(StrictModel):
    """Repository-wide execution and caller-resource defaults."""

    timeout_seconds: int = Field(default=600, gt=0)
    output_limit_bytes: int = Field(default=1_048_576, ge=4096, le=16_777_216)
    # Bound the complete caller input mapping before type conversion. The same limit also caps
    # the encoded arbitrary-string JSON payload written for a task invocation.
    input_limit_bytes: int = Field(default=1_048_576, ge=1, le=16_777_216)


class ContextConfig(StrictModel):
    """Relative repository directory defining one governed execution context."""

    directory: str


class TaskConfig(StrictModel):
    """Governed exposure, metadata, limits, and input contract for one Make target."""

    enabled: bool = True
    contexts: list[str] = Field(default_factory=lambda: ["root"])
    description: str | None = None
    risk: TaskRisk | None = None
    timeout_seconds: int | None = Field(default=None, gt=0)
    variables: dict[str, VariableSpec] = Field(default_factory=dict)

    @field_validator("contexts")
    @classmethod
    def unique_contexts(cls, value: list[str]) -> list[str]:
        """Require at least one context and remove duplicate names deterministically."""
        if not value:
            raise ValueError("task contexts must not be empty")
        return list(dict.fromkeys(value))

    @field_validator("variables")
    @classmethod
    def valid_variable_names(cls, value: dict[str, VariableSpec]) -> dict[str, VariableSpec]:
        """Require names safe for Make transport and generated direct MCP signatures."""
        return _validate_task_variable_mapping(value)


class EnvironmentConfig(StrictModel):
    """Explicit child-process environment inherited or injected by governed policy."""

    inherit: list[str] = Field(default_factory=lambda: ["PATH", "HOME", "USER"])
    allow: dict[str, str] = Field(default_factory=dict)

    @field_validator("inherit")
    @classmethod
    def unique_inherit(cls, value: list[str]) -> list[str]:
        """Validate and de-duplicate inherited environment names."""
        invalid = [name for name in value if not is_identifier_name(name)]
        if invalid:
            raise ValueError(f"invalid inherited environment names: {', '.join(sorted(invalid))}")
        reserved = sorted(set(value) & RESERVED_MAKE_VARIABLES)
        if reserved:
            raise ValueError(
                "GNU Make/Make MCP control variables cannot be inherited: " + ", ".join(reserved)
            )
        return list(dict.fromkeys(value))

    @field_validator("allow")
    @classmethod
    def valid_allowed_names(cls, value: dict[str, str]) -> dict[str, str]:
        """Validate configured environment names and reject Make control variables."""
        invalid = [name for name in value if not is_identifier_name(name)]
        if invalid:
            raise ValueError(f"invalid allowed environment names: {', '.join(sorted(invalid))}")
        reserved = sorted(set(value) & RESERVED_MAKE_VARIABLES)
        if reserved:
            raise ValueError(
                "GNU Make/Make MCP control variables cannot be configured: " + ", ".join(reserved)
            )
        return value


class MakeMcpConfig(StrictModel):
    """Validated contents of one optional ``.make-mcp.yaml`` policy file."""

    schema_version: int = 1
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    contexts: dict[str, ContextConfig] = Field(default_factory=dict)
    tasks: dict[str, TaskConfig] = Field(default_factory=dict)
    capabilities: dict[str, str] = Field(default_factory=dict)
    environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)

    @field_validator("schema_version")
    @classmethod
    def only_v1(cls, value: int) -> int:
        """Reject configuration schemas not understood by this release."""
        if value != 1:
            raise ValueError("only schema_version: 1 is supported")
        return value

    @field_validator("contexts")
    @classmethod
    def valid_context_names(cls, value: dict[str, ContextConfig]) -> dict[str, ContextConfig]:
        """Validate context names and reserve ``root`` for the repository root."""
        invalid = [name for name in value if not CONTEXT_NAME_PATTERN.fullmatch(name)]
        if invalid:
            raise ValueError(f"invalid context names: {', '.join(sorted(invalid))}")
        if "root" in value:
            raise ValueError("context name 'root' is reserved for the repository root")
        return value

    @model_validator(mode="after")
    def validate_task_contexts(self) -> "MakeMcpConfig":
        """Ensure every configured task references only declared contexts."""
        known = {"root", *self.contexts}
        invalid: list[str] = []
        for task_name, task in self.tasks.items():
            invalid.extend(
                f"{task_name}:{context}" for context in task.contexts if context not in known
            )
        if invalid:
            raise ValueError("tasks reference unknown contexts: " + ", ".join(sorted(invalid)))
        return self
