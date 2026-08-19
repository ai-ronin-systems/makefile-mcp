"""Stable Make MCP data contracts and configuration models."""

import re
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskRisk(StrEnum):
    SAFE = "safe"
    WRITE = "write"
    DANGEROUS = "dangerous"


class VariableType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ENUM = "enum"
    PATH = "path"


class TaskStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class DoctorSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class TaskVariable(StrictModel):
    type: VariableType = VariableType.STRING
    required: bool = False
    description: str | None = None
    values: list[str] = Field(default_factory=list)
    default: str | int | bool | None = None


class TaskDefinition(StrictModel):
    name: str
    description: str | None = None
    context: str = "root"
    risk: TaskRisk = TaskRisk.SAFE
    timeout_seconds: int = Field(default=600, gt=0)
    variables: dict[str, TaskVariable] = Field(default_factory=dict)
    exposure_source: str


class ProjectContext(StrictModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    name: str
    directory: Path


class ProcessResult(StrictModel):
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    cancelled: bool = False
    truncated: bool = False
    started_at: datetime
    completed_at: datetime


class TaskResult(StrictModel):
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


class DoctorFinding(StrictModel):
    code: str
    severity: DoctorSeverity
    message: str
    context: str | None = None
    task: str | None = None


class DoctorResult(StrictModel):
    ok: bool
    findings: list[DoctorFinding] = Field(default_factory=list)


class DefaultsConfig(StrictModel):
    timeout_seconds: int = Field(default=600, gt=0)
    output_limit_bytes: int = Field(default=1_048_576, ge=4096, le=16_777_216)


class ContextConfig(StrictModel):
    directory: str


class VariableConfig(StrictModel):
    type: VariableType = VariableType.STRING
    required: bool = False
    description: str | None = None
    values: list[str] = Field(default_factory=list)
    default: str | int | bool | None = None

    @model_validator(mode="after")
    def validate_enum(self):
        if self.type == VariableType.ENUM and not self.values:
            raise ValueError("enum variables require non-empty values")
        if self.type != VariableType.ENUM and self.values:
            raise ValueError("values is only valid for enum variables")
        return self


class TaskConfig(StrictModel):
    enabled: bool = True
    description: str | None = None
    risk: TaskRisk | None = None
    timeout_seconds: int | None = Field(default=None, gt=0)
    variables: dict[str, VariableConfig] = Field(default_factory=dict)

    @field_validator("variables")
    @classmethod
    def valid_variable_names(cls, value: dict[str, VariableConfig]) -> dict[str, VariableConfig]:
        invalid = [name for name in value if not _NAME.fullmatch(name)]
        if invalid:
            raise ValueError(f"invalid Make variable names: {', '.join(sorted(invalid))}")
        return value


class EnvironmentConfig(StrictModel):
    inherit: list[str] = Field(default_factory=lambda: ["PATH", "HOME", "USER"])
    allow: dict[str, str] = Field(default_factory=dict)

    @field_validator("inherit")
    @classmethod
    def unique_inherit(cls, value: list[str]) -> list[str]:
        invalid = [name for name in value if not _NAME.fullmatch(name)]
        if invalid:
            raise ValueError(f"invalid inherited environment names: {', '.join(sorted(invalid))}")
        return list(dict.fromkeys(value))

    @field_validator("allow")
    @classmethod
    def valid_allowed_names(cls, value: dict[str, str]) -> dict[str, str]:
        invalid = [name for name in value if not _NAME.fullmatch(name)]
        if invalid:
            raise ValueError(f"invalid allowed environment names: {', '.join(sorted(invalid))}")
        return value


class MakeMcpConfig(StrictModel):
    schema_version: int = 1
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    contexts: dict[str, ContextConfig] = Field(default_factory=dict)
    tasks: dict[str, TaskConfig] = Field(default_factory=dict)
    capabilities: dict[str, str] = Field(default_factory=dict)
    environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)

    @field_validator("schema_version")
    @classmethod
    def only_v1(cls, value: int) -> int:
        if value != 1:
            raise ValueError("only schema_version: 1 is supported")
        return value
