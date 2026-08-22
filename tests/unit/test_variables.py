from pathlib import Path

import pytest

from make_mcp.errors import UnsafePathError, VariableValidationError
from make_mcp.inputs import validate_variables
from make_mcp.models import TaskDefinition, VariableSpec


def task(**variables):
    return TaskDefinition(name="test", variables=variables)


def validate(definition, supplied, root):
    return validate_variables(definition, supplied, root=root, cwd=root)


def test_unknown_variable_rejected(tmp_path: Path):
    with pytest.raises(VariableValidationError):
        validate(task(), {"EVIL": "1"}, tmp_path)


def test_enum_and_boolean_are_normalized(tmp_path: Path):
    definition = task(
        MODE=VariableSpec(type="enum", values=["fast", "full"], required=True),
        CI=VariableSpec(type="boolean"),
    )
    assert validate(definition, {"MODE": "fast", "CI": "yes"}, tmp_path) == {
        "MODE": "fast",
        "CI": "true",
    }
    with pytest.raises(VariableValidationError):
        validate(definition, {"MODE": "other"}, tmp_path)


def test_token_rejects_make_and_shell_syntax(tmp_path: Path):
    definition = task(NAME=VariableSpec(type="token"))
    for value in (
        "$(shell touch PWNED)",
        "hello;touch-PWNED",
        "hello && touch PWNED",
        "`touch PWNED`",
        "hello\nworld",
        "hello world",
    ):
        with pytest.raises(VariableValidationError):
            validate(definition, {"NAME": value}, tmp_path)

    assert validate(definition, {"NAME": "pkg/sub.module-v2@prod"}, tmp_path) == {
        "NAME": "pkg/sub.module-v2@prod"
    }


def test_path_escape_symlink_and_unsafe_syntax_rejected(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    definition = task(REPORT=VariableSpec(type="path"))
    with pytest.raises(UnsafePathError):
        validate(definition, {"REPORT": "../outside.txt"}, tmp_path)
    with pytest.raises(UnsafePathError):
        validate(definition, {"REPORT": "link/out.txt"}, tmp_path)
    with pytest.raises(VariableValidationError):
        validate(definition, {"REPORT": "reports/$(shell-touch)/out.json"}, tmp_path)
    assert validate(definition, {"REPORT": "reports/out.json"}, tmp_path)["REPORT"].endswith(
        "reports/out.json"
    )


def test_runtime_task_contract_rejects_reserved_make_variable():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="reserved"):
        task(SHELL=VariableSpec(type="token"))


def test_zero_config_task_rejects_caller_variables(app_for):
    import asyncio

    from make_mcp.errors import VariableValidationError

    app = app_for("test:\n\t@true\n")
    with pytest.raises(VariableValidationError, match="undeclared variables"):
        asyncio.run(app.run_task("test", {"ANYTHING": "value"}))


def test_runtime_input_mapping_requires_string_keys_and_values(tmp_path: Path):
    definition = task(NAME=VariableSpec(type="token"))

    with pytest.raises(VariableValidationError, match="must be a mapping"):
        validate(definition, ["NAME=value"], tmp_path)  # type: ignore[arg-type]

    with pytest.raises(VariableValidationError, match="names must be strings"):
        validate(definition, {1: "value"}, tmp_path)  # type: ignore[dict-item]

    with pytest.raises(VariableValidationError, match="values must be strings"):
        validate(definition, {"NAME": 123}, tmp_path)  # type: ignore[dict-item]


def test_unpaired_unicode_surrogate_is_normalized_to_validation_error(tmp_path: Path):
    definition = task(MESSAGE=VariableSpec(type="string"))
    with pytest.raises(VariableValidationError, match="valid UTF-8"):
        validate(definition, {"MESSAGE": "\ud800"}, tmp_path)
