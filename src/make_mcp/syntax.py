"""Shared lexical rules for safe Make/MCP boundary values.

The module is intentionally small: it centralizes grammars that must stay identical across
configuration validation, execution validation, and generated MCP tool signatures.
"""

import keyword
import re

VARIABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SAFE_LITERAL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:+-]*$")
SAFE_PATH_PATTERN = re.compile(r"^[A-Za-z0-9._/@:+/-]+$")
CONTEXT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

BOOLEAN_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
BOOLEAN_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
BOOLEAN_VALUES = BOOLEAN_TRUE_VALUES | BOOLEAN_FALSE_VALUES

# MAKE_MCP_INPUT is owned by the executor. String inputs are serialized to a private JSON
# payload and only this generated pathname is transported through GNU Make.
MAKE_MCP_INPUT_VARIABLE = "MAKE_MCP_INPUT"
MCP_CONTROL_PARAMETER_NAMES = frozenset({"preview"})

# GNU Make control variables can alter parser, include, shell, recursion, search-path or
# execution behavior. They are never caller task inputs or configurable inherited values.
RESERVED_MAKE_VARIABLES = frozenset(
    {
        "CURDIR",
        "GNUMAKEFLAGS",
        "GPATH",
        "MAKE",
        "MAKECMDGOALS",
        "MAKEFILE_LIST",
        "MAKEFILES",
        "MAKEFLAGS",
        "MAKELEVEL",
        "MAKEOVERRIDES",
        "MAKE_RESTARTS",
        "MAKE_TERMERR",
        "MAKE_TERMOUT",
        "MAKE_VERSION",
        "MFLAGS",
        "SHELL",
        "VPATH",
        MAKE_MCP_INPUT_VARIABLE,
    }
)


def is_identifier_name(name: str) -> bool:
    """Return whether *name* uses Make MCP's simple identifier grammar."""
    return bool(VARIABLE_NAME_PATTERN.fullmatch(name))


def is_task_variable_name(name: str) -> bool:
    """Return whether a task variable can also be represented as a Python MCP parameter.

    Direct MCP tools derive their JSON schema from Python call signatures. Python keywords
    such as ``class`` or ``async`` therefore cannot be task-variable names even though GNU
    Make itself would accept them.
    """
    return is_identifier_name(name) and not keyword.iskeyword(name)


def parse_boolean_literal(raw: str) -> bool:
    """Parse one accepted boolean literal.

    Args:
        raw: Text accepted by Make MCP's boolean grammar.

    Returns:
        ``True`` or ``False``.

    Raises:
        ValueError: If *raw* is outside the accepted boolean vocabulary.
    """
    lowered = raw.lower()
    if lowered in BOOLEAN_TRUE_VALUES:
        return True
    if lowered in BOOLEAN_FALSE_VALUES:
        return False
    raise ValueError(f"expected boolean, got {raw!r}")
