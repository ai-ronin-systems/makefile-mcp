import json

from typer.testing import CliRunner

from makefile_mcp.cli import cli
from makefile_mcp.version import __version__


def _runner() -> CliRunner:
    return CliRunner()


def test_global_version_flag_reports_package_version_without_repository_bootstrap():
    result = _runner().invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_list_and_list_json_expose_discovered_tasks(tmp_path):
    (tmp_path / "Makefile").write_text("hello: ## Say hello\n\t@echo hello\n", encoding="utf-8")

    text_result = _runner().invoke(cli, ["--root", str(tmp_path), "list"])
    json_result = _runner().invoke(cli, ["--root", str(tmp_path), "list", "--json"])

    assert text_result.exit_code == 0
    assert "hello" in text_result.stdout
    assert "Say hello" in text_result.stdout
    payload = json.loads(json_result.stdout)
    assert [task["name"] for task in payload] == ["hello"]
    assert payload[0]["description"] == "Say hello"


def test_describe_and_describe_json_expose_governed_contract(tmp_path):
    (tmp_path / "Makefile").write_text("deploy:\n\t@echo deploy\n", encoding="utf-8")
    (tmp_path / ".makefile-mcp.yaml").write_text(
        "schema_version: 1\n"
        "tasks:\n"
        "  deploy:\n"
        "    description: Deploy safely\n"
        "    risk: dangerous\n"
        "    timeout_seconds: 12\n"
        "    variables:\n"
        "      ENV:\n"
        "        type: enum\n"
        "        required: true\n"
        "        values: [staging, production]\n",
        encoding="utf-8",
    )

    text_result = _runner().invoke(cli, ["--root", str(tmp_path), "describe", "deploy"])
    json_result = _runner().invoke(cli, ["--root", str(tmp_path), "describe", "deploy", "--json"])

    assert text_result.exit_code == 0
    assert "Task: deploy" in text_result.stdout
    assert "Risk: dangerous" in text_result.stdout
    assert "ENV: enum (required)" in text_result.stdout
    payload = json.loads(json_result.stdout)
    assert payload["name"] == "deploy"
    assert payload["timeout_seconds"] == 12
    assert payload["variables"]["ENV"]["values"] == ["staging", "production"]


def test_run_preview_uses_make_dry_run(tmp_path):
    (tmp_path / "Makefile").write_text(
        ".PHONY: write\nwrite:\n\t@touch preview-marker\n", encoding="utf-8"
    )

    result = _runner().invoke(cli, ["--root", str(tmp_path), "run", "write", "--preview"])

    assert result.exit_code == 0
    assert "[preview]" in result.stdout
    assert "touch preview-marker" in result.stdout
    assert not (tmp_path / "preview-marker").exists()


def test_run_json_returns_normalized_success_result(tmp_path):
    (tmp_path / "Makefile").write_text("ok:\n\t@echo hello\n", encoding="utf-8")

    result = _runner().invoke(cli, ["--root", str(tmp_path), "run", "ok", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["task"] == "ok"
    assert payload["status"] == "passed"
    assert payload["preview"] is False
    assert "hello" in payload["stdout"]


def test_run_failed_task_exits_one_and_preserves_task_output(tmp_path):
    (tmp_path / "Makefile").write_text("fail:\n\t@echo boom >&2; exit 7\n", encoding="utf-8")

    result = _runner().invoke(cli, ["--root", str(tmp_path), "run", "fail"])

    assert result.exit_code == 1
    assert "fail: failed [run]" in result.stdout
    assert "boom" in result.stderr


def test_run_rejects_malformed_assignment_with_exit_two(tmp_path):
    (tmp_path / "Makefile").write_text("ok:\n\t@true\n", encoding="utf-8")

    result = _runner().invoke(cli, ["--root", str(tmp_path), "run", "ok", "NOT_AN_ASSIGNMENT"])

    assert result.exit_code == 2
    assert "KEY=VALUE" in result.stderr


def test_run_rejects_duplicate_assignment_with_exit_two(tmp_path):
    (tmp_path / "Makefile").write_text("ok:\n\t@true\n", encoding="utf-8")

    result = _runner().invoke(cli, ["--root", str(tmp_path), "run", "ok", "X=1", "X=2"])

    assert result.exit_code == 2
    assert "duplicate variable: X" in result.stderr


def test_unknown_task_is_domain_error_with_exit_two(tmp_path):
    (tmp_path / "Makefile").write_text("ok:\n\t@true\n", encoding="utf-8")

    result = _runner().invoke(cli, ["--root", str(tmp_path), "describe", "missing"])

    assert result.exit_code == 2
    assert "error:" in result.stderr


def test_unknown_context_is_domain_error_with_exit_two(tmp_path):
    (tmp_path / "Makefile").write_text("ok:\n\t@true\n", encoding="utf-8")

    result = _runner().invoke(cli, ["--root", str(tmp_path), "list", "--context", "missing"])

    assert result.exit_code == 2
    assert "error:" in result.stderr


def test_doctor_text_and_json_report_healthy_repository(tmp_path):
    (tmp_path / "Makefile").write_text("ok:\n\t@true\n", encoding="utf-8")

    text_result = _runner().invoke(cli, ["--root", str(tmp_path), "doctor"])
    json_result = _runner().invoke(cli, ["--root", str(tmp_path), "doctor", "--json"])

    assert text_result.exit_code == 0
    assert "doctor: ok" in text_result.stdout
    payload = json.loads(json_result.stdout)
    assert payload["ok"] is True
    assert any(finding["code"] == "exposure.auto" for finding in payload["findings"])


def test_doctor_problem_exits_one(tmp_path):
    (tmp_path / "Makefile").write_text("ok:\n\t@true\n", encoding="utf-8")
    (tmp_path / ".makefile-mcp.yaml").write_text(
        "schema_version: 1\n"
        "environment:\n"
        "  allow:\n"
        "    PATH: /definitely/not/a/real/path\n"
        "tasks:\n"
        "  ok: {}\n",
        encoding="utf-8",
    )

    result = _runner().invoke(cli, ["--root", str(tmp_path), "doctor"])

    assert result.exit_code == 1
    assert "doctor: problems found" in result.stdout
    assert "make.unavailable" in result.stdout
