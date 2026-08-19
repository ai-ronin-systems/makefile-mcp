import pytest

from makefile_mcp.errors import TaskNotExposed


def test_monorepo_context_scope_and_makefile_change_detection(repo):
    root = repo(
        ".PHONY: root\nroot: ## Root\n\t@true\n",
        "schema_version: 1\n"
        "contexts:\n"
        "  backend:\n"
        "    directory: backend\n"
        "tasks:\n"
        "  test:\n"
        "    contexts: [backend]\n"
        "  lint:\n"
        "    contexts: [backend]\n",
    )
    backend = root / "backend"
    backend.mkdir()
    (backend / "Makefile").write_text(".PHONY: test\ntest: ## Test\n\t@true\n", encoding="utf-8")
    from makefile_mcp.app import build_application

    app = build_application(root)
    assert [t.name for t in app.list_tasks("backend")] == ["test"]
    (backend / "Makefile").write_text(
        ".PHONY: test lint\ntest: ## Test\n\t@true\nlint: ## Lint\n\t@true\n",
        encoding="utf-8",
    )
    assert [t.name for t in app.list_tasks("backend")] == ["lint", "test"]


def test_same_target_name_is_not_implicitly_exposed_in_other_context(repo):
    root = repo(
        ".PHONY: test\ntest:\n\t@true\n",
        "schema_version: 1\n"
        "contexts:\n"
        "  backend:\n"
        "    directory: backend\n"
        "tasks:\n"
        "  test:\n"
        "    contexts: [root]\n",
    )
    backend = root / "backend"
    backend.mkdir()
    (backend / "Makefile").write_text(".PHONY: test\ntest:\n\t@true\n", encoding="utf-8")

    from makefile_mcp.app import build_application

    app = build_application(root)
    assert [task.name for task in app.list_tasks("root")] == ["test"]
    assert app.list_tasks("backend") == []
    with pytest.raises(TaskNotExposed):
        app.describe_task("test", "backend")


def test_config_change_fails_closed_until_application_restart(repo):
    root = repo(
        ".PHONY: a b\na:\n\t@true\nb:\n\t@true\n",
        "schema_version: 1\ntasks:\n  a: {}\n",
    )
    from makefile_mcp.app import build_application
    from makefile_mcp.errors import ConfigurationError

    app = build_application(root)
    assert [task.name for task in app.list_tasks()] == ["a"]

    (root / ".makefile-mcp.yaml").write_text(
        "schema_version: 1\ntasks:\n  b: {}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigurationError, match="changed since startup"):
        app.list_tasks()
    assert [task.name for task in build_application(root).list_tasks()] == ["b"]


def test_missing_literal_include_appearance_invalidates_cache(repo):
    root = repo(
        "-include generated.mk\n",
        "schema_version: 1\ntasks:\n  late: {}\n",
    )
    from makefile_mcp.app import build_application

    app = build_application(root)
    first = app.catalog.snapshot()
    assert app.list_tasks() == []
    assert root / "generated.mk" in first.tracked_files
    assert any("does not exist" in warning for warning in first.warnings)

    (root / "generated.mk").write_text("late:\n\t@echo LATE\n", encoding="utf-8")
    assert [task.name for task in app.list_tasks()] == ["late"]


def test_config_appearance_in_auto_mode_fails_closed(repo):
    root = repo("a:\n\t@true\n")
    from makefile_mcp.app import build_application
    from makefile_mcp.errors import ConfigurationError

    app = build_application(root)
    assert [task.name for task in app.list_tasks()] == ["a"]
    (root / ".makefile-mcp.yaml").write_text(
        "schema_version: 1\ntasks:\n  a: {}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigurationError, match="changed since startup"):
        app.list_tasks()


def test_include_symlink_retarget_invalidates_live_catalog(repo):
    root = repo("include selected.mk\n")
    (root / "a.mk").write_text("a:\n\t@true\n", encoding="utf-8")
    (root / "b.mk").write_text("b:\n\t@true\n", encoding="utf-8")
    selected = root / "selected.mk"
    selected.symlink_to("a.mk")

    from makefile_mcp.app import build_application

    app = build_application(root)
    assert [task.name for task in app.list_tasks()] == ["a"]
    selected.unlink()
    selected.symlink_to("b.mk")
    assert [task.name for task in app.list_tasks()] == ["b"]


def test_doctor_rejects_duplicate_physical_context_directories(repo):
    root = repo(
        "test:\n\t@true\n",
        "schema_version: 1\n"
        "contexts:\n"
        "  alias:\n"
        "    directory: .\n"
        "tasks:\n"
        "  test:\n"
        "    contexts: [root, alias]\n",
    )
    from makefile_mcp.app import build_application

    result = build_application(root).doctor()
    assert result.ok is False
    assert any(f.code == "context.duplicate_directory" for f in result.findings)
