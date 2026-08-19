"""Expected Makefile MCP errors surfaced consistently by CLI and MCP."""


class MakefileMcpError(Exception):
    """Base class for expected, user-facing Makefile MCP failures."""


class ConfigurationError(MakefileMcpError):
    """Invalid repository detection or ``.makefile-mcp.yaml`` configuration."""


class ContextNotFound(MakefileMcpError):
    """Requested execution context does not exist or resolve safely."""


class UnsafePathError(MakefileMcpError):
    """A supplied path is missing when required or escapes the repository boundary."""


class TaskNotFound(MakefileMcpError):
    """Requested target or semantic capability is unknown."""


class TaskNotExposed(MakefileMcpError):
    """A discovered target is hidden by governed exposure policy."""


class VariableValidationError(MakefileMcpError):
    """Caller input violates a declared task-variable contract."""


class TaskBusyError(MakefileMcpError):
    """Another process already owns the execution lock for a context."""


class MakeInspectionError(MakefileMcpError):
    """Static Make discovery cannot safely model the encountered syntax."""


class ExecutionStartError(MakefileMcpError):
    """The bounded Make subprocess could not be started."""
