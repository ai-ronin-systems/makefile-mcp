"""Expected Make MCP errors surfaced consistently by CLI and MCP."""


class MakeMcpError(Exception):
    pass


class ConfigurationError(MakeMcpError):
    pass


class ContextNotFound(MakeMcpError):
    pass


class UnsafePathError(MakeMcpError):
    pass


class TaskNotFound(MakeMcpError):
    pass


class TaskNotExposed(MakeMcpError):
    pass


class VariableValidationError(MakeMcpError):
    pass


class TaskBusyError(MakeMcpError):
    pass


class MakeUnavailableError(MakeMcpError):
    pass


class MakeInspectionError(MakeMcpError):
    pass


class ExecutionStartError(MakeMcpError):
    pass
