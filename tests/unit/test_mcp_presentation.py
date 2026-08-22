import asyncio
import inspect

from make_mcp.mcp.presentation import McpPresentation, build_direct_tools, direct_tool_base_name
from make_mcp.models import TaskDefinition


def test_presentation_has_exactly_three_modes():
    assert {mode.value for mode in McpPresentation} == {"generic", "direct", "both"}


def test_direct_tool_name_is_readable_and_context_scoped():
    assert direct_tool_base_name(TaskDefinition(name="test")) == "make_test"
    assert (
        direct_tool_base_name(TaskDefinition(name="test", context="backend")) == "make_backend_test"
    )
    assert direct_tool_base_name(TaskDefinition(name="lint:all")) == "make_lint_all"


def test_zero_config_direct_tools_are_parameterless(app_for):
    app = app_for(".PHONY: test lint\ntest: ## Run tests\n\t@true\nlint: ## Run lint\n\t@true\n")
    assert app.governed is False
    tools = build_direct_tools(app)
    assert [tool.name for tool in tools] == ["make_lint", "make_test"]
    assert all(list(inspect.signature(tool.fn).parameters) == ["preview"] for tool in tools)


def test_governed_direct_tool_signature_comes_from_variable_contract(app_for):
    app = app_for(
        ".PHONY: deploy\ndeploy:\n\t@true\n",
        "schema_version: 1\n"
        "tasks:\n"
        "  deploy:\n"
        "    variables:\n"
        "      ENV:\n"
        "        type: enum\n"
        "        values: [staging, production]\n"
        "        required: true\n"
        "      WORKERS:\n"
        "        type: integer\n"
        "        default: 2\n"
        "      DRY_RUN:\n"
        "        type: boolean\n"
        "      MESSAGE:\n"
        "        type: string\n",
    )
    tool = build_direct_tools(app)[0]
    signature = inspect.signature(tool.fn)
    assert list(signature.parameters) == ["ENV", "WORKERS", "DRY_RUN", "MESSAGE", "preview"]
    assert signature.parameters["ENV"].default is inspect.Parameter.empty
    assert signature.parameters["WORKERS"].annotation is int
    assert signature.parameters["WORKERS"].default == 2
    assert signature.parameters["DRY_RUN"].annotation is bool
    assert signature.parameters["DRY_RUN"].default is None
    assert signature.parameters["MESSAGE"].annotation is str
    assert signature.parameters["preview"].annotation is bool
    assert signature.parameters["preview"].default is False


def test_direct_tool_delegates_to_common_executor(app_for):
    app = app_for(
        '.PHONY: echo\necho:\n\t@echo "MODE=$(MODE)"\n',
        "schema_version: 1\n"
        "tasks:\n"
        "  echo:\n"
        "    variables:\n"
        "      MODE:\n"
        "        type: enum\n"
        "        values: [fast, slow]\n"
        "        required: true\n",
    )
    tool = build_direct_tools(app)[0]
    response = asyncio.run(tool.fn(MODE="fast"))
    assert response["ok"] is True
    assert response["data"]["status"] == "passed"
    assert "MODE=fast" in response["data"]["stdout"]


def test_direct_tool_name_collisions_get_stable_suffixes(tmp_path):
    from make_mcp.app import build_application

    (tmp_path / "Makefile").write_text(
        ".PHONY: foo/bar foo_bar\nfoo/bar:\n\t@true\nfoo_bar:\n\t@true\n",
        encoding="utf-8",
    )
    tools = build_direct_tools(build_application(tmp_path))
    names = [tool.name for tool in tools]
    assert len(names) == len(set(names)) == 2
    assert all(name.startswith("make_foo_bar") for name in names)


def test_runtime_task_contract_rejects_python_keyword_variable_names():
    import pytest
    from pydantic import ValidationError

    from make_mcp.models import VariableSpec

    with pytest.raises(ValidationError):
        TaskDefinition(name="test", variables={"class": VariableSpec()})


def test_task_response_raises_for_non_passing_execution():
    from datetime import UTC, datetime

    import pytest

    from make_mcp.mcp.presentation import task_response
    from make_mcp.models import TaskResult, TaskStatus

    now = datetime.now(UTC)
    result = TaskResult(
        task="fail",
        context="root",
        status=TaskStatus.FAILED,
        exit_code=2,
        started_at=now,
        completed_at=now,
        duration_ms=0,
        stderr="boom",
    )
    with pytest.raises(RuntimeError, match="boom"):
        task_response(result)


def test_task_response_includes_both_stdout_and_stderr_for_failure():
    from datetime import UTC, datetime

    import pytest

    from make_mcp.mcp.presentation import task_response
    from make_mcp.models import TaskResult, TaskStatus

    now = datetime.now(UTC)
    result = TaskResult(
        task="fail",
        context="root",
        status=TaskStatus.FAILED,
        exit_code=2,
        started_at=now,
        completed_at=now,
        duration_ms=0,
        stdout="useful application diagnostic\n",
        stderr="make: *** target failed\n",
    )
    with pytest.raises(RuntimeError) as exc_info:
        task_response(result)

    message = str(exc_info.value)
    assert "stdout:\nuseful application diagnostic" in message
    assert "stderr:\nmake: *** target failed" in message


def test_task_response_diagnostic_is_bounded_in_utf8_bytes_and_marks_truncation():
    from datetime import UTC, datetime

    import pytest

    from make_mcp.mcp.presentation import task_response
    from make_mcp.models import TaskResult, TaskStatus

    now = datetime.now(UTC)
    result = TaskResult(
        task="fail",
        context="root",
        status=TaskStatus.FAILED,
        exit_code=2,
        started_at=now,
        completed_at=now,
        duration_ms=0,
        stdout="😀" * 3000,
        truncated=True,
    )

    with pytest.raises(RuntimeError) as exc_info:
        task_response(result)

    diagnostic = str(exc_info.value).split(":\n", 1)[1]
    assert len(diagnostic.encode("utf-8")) <= 8192
    assert "[task output truncated by executor]" in diagnostic
    assert "[MCP diagnostic truncated]" in diagnostic


def test_direct_tool_preview_delegates_to_common_executor(app_for):
    app = app_for(
        ".PHONY: write\nwrite:\n\t@touch preview-marker\n",
        "schema_version: 1\ntasks:\n  write: {}\n",
    )
    tool = build_direct_tools(app)[0]

    response = asyncio.run(tool.fn(preview=True))

    assert response["data"]["preview"] is True
    assert "touch preview-marker" in response["data"]["stdout"]
    assert not (app.root / "preview-marker").exists()
