from pathlib import Path

import pytest

from make_mcp.errors import TaskBusyError, VariableValidationError
from make_mcp.filesystem import FileContextLock


def test_shell_true_never_used():
    source_root = Path(__file__).parents[2] / "src"
    hits = []
    for path in source_root.rglob("*.py"):
        if "shell=True" in path.read_text(encoding="utf-8"):
            hits.append(path)
    assert not hits


@pytest.mark.asyncio
async def test_make_function_injection_is_rejected_before_make_runs(app_for, tmp_path: Path):
    marker = tmp_path / "PWNED"
    app = app_for(
        ".PHONY: show\nshow:\n\t@printf '%s\\n' \"VALUE=$(VALUE)\"\n",
        "schema_version: 1\ntasks:\n  show:\n    variables:\n      VALUE:\n        type: token\n",
    )

    with pytest.raises(VariableValidationError):
        await app.run_task("show", {"VALUE": f"$(shell touch {marker})"})
    assert not marker.exists()


@pytest.mark.asyncio
async def test_shell_metacharacter_injection_is_rejected_before_make_runs(app_for, tmp_path: Path):
    marker = tmp_path / "PWNED"
    app = app_for(
        ".PHONY: show\nshow:\n\t@echo $(VALUE)\n",
        "schema_version: 1\ntasks:\n  show:\n    variables:\n      VALUE:\n        type: token\n",
    )

    with pytest.raises(VariableValidationError):
        await app.run_task("show", {"VALUE": f"hello;touch {marker}"})
    assert not marker.exists()


def test_context_lock_is_non_blocking(tmp_path: Path):
    lock = FileContextLock(tmp_path)
    with lock.acquire("root"), pytest.raises(TaskBusyError), lock.acquire("root"):
        pass


@pytest.mark.asyncio
async def test_arbitrary_string_uses_json_file_not_make_or_shell_syntax(app_for, tmp_path: Path):
    marker = tmp_path / "PWNED"
    payload = f"hello world\n$(shell touch {marker})\n; touch {marker}\n`touch {marker}`\n☃"
    app = app_for(
        ".PHONY: show\n"
        "show:\n"
        "\t@echo $(MAKE_MCP_INPUT)\n"
        "\t@python3 -c 'import json,sys; "
        'print(json.load(open(sys.argv[1], encoding="utf-8"))["VALUE"])\' '
        '"$(MAKE_MCP_INPUT)"\n',
        "schema_version: 1\n"
        "tasks:\n"
        "  show:\n"
        "    variables:\n"
        "      VALUE:\n"
        "        type: string\n"
        "        required: true\n",
    )

    result = await app.run_task("show", {"VALUE": payload})
    assert result.status == "passed"
    assert payload in result.stdout
    assert not marker.exists()

    # The first recipe line exposes only the generated path for this regression check. The
    # private invocation file must already be gone when run_task returns.
    input_path = Path(result.stdout.splitlines()[0])
    assert input_path.name == "input.json"
    assert not input_path.exists()
    assert not input_path.parent.exists()


@pytest.mark.asyncio
async def test_string_payload_exists_consistently_when_optional_value_is_omitted(app_for):
    app = app_for(
        ".PHONY: show\n"
        "show:\n"
        "\t@python3 -c 'import json,sys; "
        "print(json.dumps(json.load(open(sys.argv[1]))))' "
        '"$(MAKE_MCP_INPUT)"\n',
        "schema_version: 1\n"
        "tasks:\n"
        "  show:\n"
        "    variables:\n"
        "      OPTIONAL:\n"
        "        type: string\n",
    )
    result = await app.run_task("show")
    assert result.status == "passed"
    assert "{}" in result.stdout


@pytest.mark.asyncio
async def test_string_payload_is_bounded_before_make_runs(app_for, tmp_path: Path):
    marker = tmp_path / "RAN"
    app = app_for(
        ".PHONY: show\nshow:\n\t@touch " + str(marker) + "\n",
        "schema_version: 1\n"
        "defaults:\n"
        "  input_limit_bytes: 64\n"
        "tasks:\n"
        "  show:\n"
        "    variables:\n"
        "      VALUE:\n"
        "        type: string\n"
        "        required: true\n",
    )

    with pytest.raises(VariableValidationError, match="exceeds limit"):
        await app.run_task("show", {"VALUE": "x" * 128})
    assert not marker.exists()


@pytest.mark.asyncio
async def test_complete_caller_input_is_bounded_before_make_runs(app_for, tmp_path: Path):
    marker = tmp_path / "RAN_TOKEN"
    app = app_for(
        ".PHONY: show\nshow:\n\t@touch " + str(marker) + "\n",
        "schema_version: 1\n"
        "defaults:\n"
        "  input_limit_bytes: 64\n"
        "tasks:\n"
        "  show:\n"
        "    variables:\n"
        "      VALUE:\n"
        "        type: token\n"
        "        required: true\n",
    )

    with pytest.raises(VariableValidationError, match="caller input exceeds limit"):
        await app.run_task("show", {"VALUE": "x" * 128})
    assert not marker.exists()


def test_physical_context_directory_is_the_lock_identity(tmp_path: Path):
    lock = FileContextLock(tmp_path)
    directory = tmp_path / "same"
    directory.mkdir()
    with (
        lock.acquire("first", directory=directory),
        pytest.raises(TaskBusyError),
        lock.acquire("alias", directory=directory),
    ):
        pass
