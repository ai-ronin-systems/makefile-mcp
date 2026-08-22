def test_capability_is_simple_mapping(app_for):
    app = app_for(
        ".PHONY: test\ntest: ## Test\n\t@true\n",
        "schema_version: 1\ntasks:\n  test: {}\ncapabilities:\n  verify: test\n",
    )
    assert app.resolve_capability("verify").name == "test"


def test_capabilities_are_filtered_by_context(tmp_path):
    from make_mcp.app import build_application

    repo = tmp_path
    backend = repo / "backend"
    frontend = repo / "frontend"
    backend.mkdir()
    frontend.mkdir()
    (repo / "Makefile").write_text("root-task:\n\t@true\n", encoding="utf-8")
    (backend / "Makefile").write_text("test:\n\t@true\n", encoding="utf-8")
    (frontend / "Makefile").write_text("test:\n\t@true\n", encoding="utf-8")
    (repo / ".make-mcp.yaml").write_text(
        "schema_version: 1\n"
        "contexts:\n"
        "  backend: {directory: backend}\n"
        "  frontend: {directory: frontend}\n"
        "tasks:\n"
        "  test:\n"
        "    contexts: [backend]\n"
        "capabilities:\n"
        "  verify: test\n",
        encoding="utf-8",
    )
    app = build_application(repo)
    assert app.list_capabilities("backend") == {"verify": "test"}
    assert app.list_capabilities("frontend") == {}
