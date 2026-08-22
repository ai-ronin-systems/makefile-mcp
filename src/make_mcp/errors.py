"""Expected Make MCP errors surfaced consistently by CLI and MCP."""


class MakeMcpError(Exception):
    """Base class for expected, user-facing Make MCP failures."""


class ConfigurationError(MakeMcpError):
    """Invalid repository detection or ``.make-mcp.yaml`` configuration."""


class ContextNotFound(MakeMcpError):
    """Requested execution context does not exist or resolve safely."""


class UnsafePathError(MakeMcpError):
    """A supplied path is missing when required or escapes the repository boundary."""


class TaskNotFound(MakeMcpError):
    """Requested target or semantic capability is unknown."""


class TaskNotExposed(MakeMcpError):
    """A discovered target is hidden by governed exposure policy."""


class VariableValidationError(MakeMcpError):
    """Caller input violates a declared task-variable contract."""


class TaskBusyError(MakeMcpError):
    """Another process already owns the execution lock for a context."""


class MakeInspectionError(MakeMcpError):
    """Static Make discovery cannot safely model the encountered syntax."""


class ExecutionStartError(MakeMcpError):
    """The bounded Make subprocess could not be started."""
