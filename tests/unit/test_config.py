import pytest

from make_mcp.config import load_config
from make_mcp.errors import ConfigurationError


def test_config_rejects_command_field(repo):
    root = repo(
        "test:\n\t@true\n",
        "schema_version: 1\ntasks:\n  test:\n    command: echo nope\n",
    )
    with pytest.raises(ConfigurationError):
        load_config(root)


def test_config_rejects_enum_without_values(repo):
    root = repo(
        "test:\n\t@true\n",
        "schema_version: 1\ntasks:\n  test:\n    variables:\n      MODE:\n        type: enum\n",
    )
    with pytest.raises(ConfigurationError):
        load_config(root)
