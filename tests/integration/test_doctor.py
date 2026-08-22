def test_doctor_warns_for_dangerous_public_task(app_for):
    app = app_for(
        ".PHONY: destroy\ndestroy: ## Destroy\n\t@true\n",
        "schema_version: 1\ntasks:\n  destroy:\n    risk: dangerous\n",
    )
    result = app.doctor()
    assert result.ok
    assert any(f.code == "task.dangerous_public" for f in result.findings)


def test_doctor_checks_task_in_each_authorized_context(repo):
    root = repo(
        ".PHONY: test\ntest:\n\t@true\n",
        "schema_version: 1\n"
        "contexts:\n"
        "  backend:\n"
        "    directory: backend\n"
        "tasks:\n"
        "  test:\n"
        "    contexts: [root, backend]\n",
    )
    backend = root / "backend"
    backend.mkdir()
    (backend / "Makefile").write_text(".PHONY: other\nother:\n\t@true\n", encoding="utf-8")

    from make_mcp.app import build_application

    result = build_application(root).doctor()
    assert not result.ok
    assert any(
        finding.code == "task.missing" and finding.context == "backend" and finding.task == "test"
        for finding in result.findings
    )


def test_doctor_warns_that_auto_mode_is_permissive(app_for):
    result = app_for("test:\n\t@true\n").doctor()
    assert result.ok
    finding = next(f for f in result.findings if f.code == "exposure.auto")
    assert finding.severity == "warning"
    assert "governed" in finding.message


def test_doctor_does_not_emit_auto_warning_in_governed_mode(app_for):
    result = app_for(
        "test:\n\t@true\n",
        "schema_version: 1\ntasks:\n  test: {}\n",
    ).doctor()
    assert result.ok
    assert all(f.code != "exposure.auto" for f in result.findings)


def test_doctor_checks_make_against_effective_child_path(app_for):
    app = app_for(
        "test:\n\t@true\n",
        "schema_version: 1\n"
        "environment:\n"
        "  allow:\n"
        "    PATH: /definitely/not/a/real/path\n"
        "tasks:\n"
        "  test: {}\n",
    )
    result = app.doctor()
    assert not result.ok
    finding = next(f for f in result.findings if f.code == "make.unavailable")
    assert finding.severity == "error"
