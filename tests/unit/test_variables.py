from pathlib import Path

import pytest

from make_mcp.core.execution import validate_variables
from make_mcp.errors import VariableValidationError
from make_mcp.models import TaskDefinition, TaskVariable


def task(**variables):
    return TaskDefinition(name="test", variables=variables, exposure_source="config")


def validate(definition, supplied, root):
    return validate_variables(definition, supplied, root=root, cwd=root)


def test_unknown_variable_rejected(tmp_path: Path):
    with pytest.raises(VariableValidationError):
        validate(task(), {"EVIL": "1"}, tmp_path)


def test_enum_and_boolean_are_normalized(tmp_path: Path):
    definition = task(
        MODE=TaskVariable(type="enum", values=["fast", "full"], required=True),
        CI=TaskVariable(type="boolean"),
    )
    assert validate(definition, {"MODE": "fast", "CI": "yes"}, tmp_path) == {
        "MODE": "fast",
        "CI": "true",
    }
    with pytest.raises(VariableValidationError):
        validate(definition, {"MODE": "other"}, tmp_path)


def test_control_chars_rejected(tmp_path: Path):
    with pytest.raises(VariableValidationError):
        validate(task(NAME=TaskVariable()), {"NAME": "x\ny"}, tmp_path)


def test_path_escape_and_symlink_escape_rejected(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    definition = task(REPORT=TaskVariable(type="path"))
    with pytest.raises(Exception):
        validate(definition, {"REPORT": "../outside.txt"}, tmp_path)
    with pytest.raises(Exception):
        validate(definition, {"REPORT": "link/out.txt"}, tmp_path)
    assert validate(definition, {"REPORT": "reports/out.json"}, tmp_path)["REPORT"].endswith(
        "reports/out.json"
    )
