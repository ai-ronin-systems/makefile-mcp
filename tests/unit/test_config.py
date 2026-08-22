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


def test_config_accepts_string_type_for_json_file_transport(repo):
    root = repo(
        "test:\n\t@true\n",
        "schema_version: 1\ntasks:\n  test:\n    variables:\n      VALUE:\n        type: string\n",
    )
    config = load_config(root)
    assert config.tasks["test"].variables["VALUE"].type == "string"


def test_config_rejects_enum_without_values(repo):
    root = repo(
        "test:\n\t@true\n",
        "schema_version: 1\ntasks:\n  test:\n    variables:\n      MODE:\n        type: enum\n",
    )
    with pytest.raises(ConfigurationError):
        load_config(root)


def test_config_rejects_unsafe_enum_values(repo):
    root = repo(
        "test:\n\t@true\n",
        "schema_version: 1\ntasks:\n  test:\n    variables:\n      MODE:\n"
        "        type: enum\n        values: [fast, '$(shell touch PWNED)']\n",
    )
    with pytest.raises(ConfigurationError):
        load_config(root)


def test_config_rejects_reserved_make_variables(repo):
    for name in ("SHELL", "MAKEFLAGS", "MAKEFILES"):
        root = repo(
            "test:\n\t@true\n",
            f"schema_version: 1\ntasks:\n  test:\n    variables:\n      {name}: {{}}\n",
        )
        with pytest.raises(ConfigurationError):
            load_config(root)


def test_config_rejects_unknown_task_context(repo):
    root = repo(
        "test:\n\t@true\n",
        "schema_version: 1\ntasks:\n  test:\n    contexts: [missing]\n",
    )
    with pytest.raises(ConfigurationError):
        load_config(root)


def test_config_rejects_make_control_variables_in_environment(repo):
    for section in (
        "inherit: [PATH, MAKEFILES]",
        "allow:\n    MAKEFLAGS: --eval=bad",
        "allow:\n    MAKE_MCP_INPUT: /tmp/attacker.json",
    ):
        root = repo(
            "test:\n\t@true\n",
            "schema_version: 1\nenvironment:\n  " + section + "\ntasks:\n  test: {}\n",
        )
        with pytest.raises(ConfigurationError):
            load_config(root)


def test_config_rejects_unsafe_or_reserved_context_names(repo):
    for name in ("root", "foo/bar", "bad context"):
        root = repo(
            "test:\n\t@true\n",
            f"schema_version: 1\ncontexts:\n  {name!r}:\n    directory: .\ntasks:\n  test: {{}}\n",
        )
        with pytest.raises(ConfigurationError):
            load_config(root)


def test_config_rejects_python_keyword_task_variables(repo):
    for name in ("class", "from", "async"):
        root = repo(
            "test:\n\t@true\n",
            f"schema_version: 1\ntasks:\n  test:\n    variables:\n      {name}: {{}}\n",
        )
        with pytest.raises(ConfigurationError):
            load_config(root)


def test_config_rejects_required_variable_with_default(repo):
    root = repo(
        "deploy:\n\t@true\n",
        "schema_version: 1\n"
        "tasks:\n"
        "  deploy:\n"
        "    variables:\n"
        "      ENV:\n"
        "        type: enum\n"
        "        values: [staging, production]\n"
        "        required: true\n"
        "        default: staging\n",
    )
    with pytest.raises(ConfigurationError, match="required variables cannot define a default"):
        load_config(root)


def test_config_rejects_preview_as_task_variable_name(repo):
    root = repo(
        "test:\n\t@true\n",
        "schema_version: 1\ntasks:\n  test:\n    variables:\n      preview: {}\n",
    )
    with pytest.raises(ConfigurationError, match="reserved for JMIM tool controls"):
        load_config(root)
