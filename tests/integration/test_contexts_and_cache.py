from pathlib import Path


def test_monorepo_context_and_change_detection(repo):
    root = repo(".PHONY: root\nroot: ## Root\n\t@true\n", "schema_version: 1\ncontexts:\n  backend:\n    directory: backend\n")
    backend = root / "backend"
    backend.mkdir()
    (backend / "Makefile").write_text(".PHONY: test\ntest: ## Test\n\t@true\n", encoding="utf-8")
    from make_mcp.app import build_application
    app = build_application(root)
    assert [t.name for t in app.list_tasks("backend")] == ["test"]
    (backend / "Makefile").write_text(".PHONY: test lint\ntest: ## Test\n\t@true\nlint: ## Lint\n\t@true\n", encoding="utf-8")
    assert [t.name for t in app.list_tasks("backend")] == ["lint", "test"]
