import pytest

from makefile_mcp.errors import TaskNotExposed, TaskNotFound


def test_only_enabled_configured_targets_are_exposed(app_for):
    app = app_for(
        ".PHONY: phony\n"
        "documented: ## Documentation alone is not authorization\n\t@true\n"
        "phony:\n\t@true\n"
        "private:\n\t@true\n"
        "configured:\n\t@true\n",
        "schema_version: 1\ntasks:\n  configured:\n    risk: write\n",
    )
    tasks = {task.name: task for task in app.list_tasks()}
    assert set(tasks) == {"configured"}
    assert tasks["configured"].risk == "write"
    for hidden in ("documented", "phony", "private"):
        with pytest.raises(TaskNotExposed):
            app.describe_task(hidden)


def test_disabled_target_stays_hidden(app_for):
    app = app_for(
        ".PHONY: deploy\ndeploy: ## Deploy\n\t@true\n",
        "schema_version: 1\ntasks:\n  deploy:\n    enabled: false\n",
    )
    assert app.list_tasks() == []
    with pytest.raises(TaskNotExposed):
        app.describe_task("deploy")


def test_risk_defaults_to_unknown_instead_of_name_inference(app_for):
    app = app_for(
        ".PHONY: destroy-production\ndestroy-production:\n\t@true\n",
        "schema_version: 1\ntasks:\n  destroy-production: {}\n",
    )
    assert app.describe_task("destroy-production").risk == "unknown"


def test_nested_literal_include_resolution_matches_make_invocation_directory(repo):
    root = repo(
        "include sub/one.mk\n",
        "schema_version: 1\ntasks:\n  deploy: {}\n",
    )
    sub = root / "sub"
    sub.mkdir()
    (sub / "one.mk").write_text("include two.mk\n", encoding="utf-8")
    (sub / "two.mk").write_text(
        "deploy: ## Wrong nested-relative file\n\t@echo WRONG\n",
        encoding="utf-8",
    )
    (root / "two.mk").write_text(
        "deploy: ## Root include used by GNU Make\n\t@echo ROOT\n",
        encoding="utf-8",
    )

    from makefile_mcp.app import build_application

    app = build_application(root)
    definition = app.describe_task("deploy")
    snapshot = app.catalog.snapshot()
    assert definition.description == "Root include used by GNU Make"
    assert root / "two.mk" in snapshot.tracked_files
    assert sub / "two.mk" not in snapshot.tracked_files


def test_unsupported_include_is_warned_and_never_creates_false_positive_target(repo):
    root = repo(
        "include *.mk\n",
        "schema_version: 1\ntasks:\n  surprise: {}\n",
    )
    (root / "extra.mk").write_text("surprise:\n\t@echo nope\n", encoding="utf-8")

    from makefile_mcp.app import build_application

    app = build_application(root)
    snapshot = app.catalog.snapshot()
    assert app.list_tasks() == []
    assert "surprise" not in snapshot.discovered_targets
    assert any(
        "dynamic/unsupported include not tracked" in warning for warning in snapshot.warnings
    )


def test_inactive_conditional_cannot_create_false_positive_target(repo):
    root = repo(
        "ACTUAL = actual.mk\nifeq (1,0)\ndeploy:\n\t@echo STATIC_SAFE\nendif\ninclude $(ACTUAL)\n",
        "schema_version: 1\ntasks:\n  deploy: {}\n",
    )
    (root / "actual.mk").write_text("deploy:\n\t@echo ACTUAL_DYNAMIC\n", encoding="utf-8")

    from makefile_mcp.app import build_application

    app = build_application(root)
    snapshot = app.catalog.snapshot()
    assert app.list_tasks() == []
    assert "deploy" not in snapshot.discovered_targets
    assert any("conditional Make block not statically inspected" in w for w in snapshot.warnings)


def test_define_body_cannot_create_false_positive_target(repo):
    root = repo(
        "ACTUAL = actual.mk\n"
        "define TEMPLATE\n"
        "ghost:\n\t@echo STATIC_SAFE\n"
        "endef\n"
        "include $(ACTUAL)\n",
        "schema_version: 1\ntasks:\n  ghost: {}\n",
    )
    (root / "actual.mk").write_text("ghost:\n\t@echo ACTUAL_DYNAMIC\n", encoding="utf-8")

    from makefile_mcp.app import build_application

    app = build_application(root)
    snapshot = app.catalog.snapshot()
    assert app.list_tasks() == []
    assert "ghost" not in snapshot.discovered_targets
    assert any("define block not statically inspected" in w for w in snapshot.warnings)


def test_custom_recipeprefix_fails_closed(repo):
    root = repo(
        ".RECIPEPREFIX = >\nsafe:\n>echo fake:\n",
        "schema_version: 1\ntasks:\n  fake: {}\n",
    )

    from makefile_mcp.app import build_application
    from makefile_mcp.errors import MakeInspectionError

    with pytest.raises(MakeInspectionError, match="RECIPEPREFIX"):
        build_application(root).list_tasks()


def test_zero_config_auto_exposes_all_conservatively_discovered_targets(app_for):
    app = app_for(
        ".PHONY: test lint\n"
        "test: ## Run tests\n\t@true\n"
        "lint: ## Run lint\n\t@true\n"
        "private-looking:\n\t@true\n"
    )
    assert app.governed is False
    tasks = {task.name: task for task in app.list_tasks()}
    assert set(tasks) == {"test", "lint", "private-looking"}
    assert all(task.variables == {} for task in tasks.values())
    assert all(task.risk == "unknown" for task in tasks.values())


def test_config_presence_switches_to_governed_deny_by_default(app_for):
    app = app_for(
        "public:\n\t@true\nhidden:\n\t@true\n",
        "schema_version: 1\ntasks:\n  public: {}\n",
    )
    assert app.governed is True
    assert [task.name for task in app.list_tasks()] == ["public"]
    with pytest.raises(TaskNotExposed):
        app.describe_task("hidden")


def test_empty_config_is_governed_and_exposes_nothing(app_for):
    app = app_for("test:\n\t@true\n", "{}\n")
    assert app.governed is True
    assert app.list_tasks() == []
    with pytest.raises(TaskNotExposed):
        app.describe_task("test")


def test_modified_define_forms_cannot_create_false_positive_targets(repo):
    root = repo(
        "override define TEMPLATE\n"
        "ghost:\n\t@echo DATA\n"
        "endef\n"
        "export define OTHER\n"
        "phantom:\n\t@echo DATA\n"
        "endef\n"
        "private define THIRD\n"
        "shadow:\n\t@echo DATA\n"
        "endef\n"
        "safe:\n\t@true\n",
        "schema_version: 1\ntasks:\n  ghost: {}\n  phantom: {}\n  shadow: {}\n  safe: {}\n",
    )

    from makefile_mcp.app import build_application

    app = build_application(root)
    snapshot = app.catalog.snapshot()
    assert [task.name for task in app.list_tasks()] == ["safe"]
    assert not ({"ghost", "phantom", "shadow"} & snapshot.discovered_targets)


def test_recipeprefix_word_in_comment_or_description_is_not_assignment(app_for):
    app = app_for(
        "test: ## Explain .RECIPEPREFIX behavior\n\t@true\n"
        "# .RECIPEPREFIX = > is intentionally unsupported\n"
    )
    assert [task.name for task in app.list_tasks()] == ["test"]


def test_common_dependency_and_double_colon_rules_are_discovered(app_for):
    app = app_for("dep:\n\t@true\ntest:dep\n\t@true\ndouble::\n\t@true\n")
    assert [task.name for task in app.list_tasks()] == ["dep", "double", "test"]


def test_required_literal_include_fails_closed_but_optional_missing_include_is_allowed(repo):
    from makefile_mcp.app import build_application
    from makefile_mcp.errors import MakeInspectionError

    root = repo("include required.mk\n")
    with pytest.raises(MakeInspectionError, match="required included Makefile"):
        build_application(root).list_tasks()

    (root / "Makefile").write_text("-include optional.mk\nsafe:\n\t@true\n", encoding="utf-8")
    app = build_application(root)
    snapshot = app.catalog.snapshot()
    assert [task.name for task in app.list_tasks()] == ["safe"]
    assert any("optional included Makefile does not exist" in w for w in snapshot.warnings)


def test_phony_description_words_are_not_discovered_as_targets(app_for):
    app = app_for(".PHONY: test ## Run the full suite\ntest:\n\t@true\n")
    assert [task.name for task in app.list_tasks()] == ["test"]


def test_target_looking_recipe_continuation_is_not_discovered(app_for):
    app = app_for("safe:\n\t@printf '%s\\n' hello \\\nghost:\n\t@true\n")
    assert [task.name for task in app.list_tasks()] == ["safe"]


def test_literal_include_allows_trailing_comment(repo):
    root = repo("include rules.mk # trusted literal include\n")
    (root / "rules.mk").write_text("included:\n\t@true\n", encoding="utf-8")

    from makefile_mcp.app import build_application

    assert [task.name for task in build_application(root).list_tasks()] == ["included"]


def test_variable_continuation_cannot_create_false_positive_target(app_for):
    app = app_for("VALUE = data \\\nghost:\nsafe:\n\t@true\n")
    assert [task.name for task in app.list_tasks()] == ["safe"]


def test_target_specific_assignment_does_not_define_callable_target(app_for):
    app = app_for("ghost: VALUE := data\nsafe:\n\t@true\n")
    assert [task.name for task in app.list_tasks()] == ["safe"]


def test_colon_style_variable_assignment_is_not_discovered_as_target(app_for):
    app = app_for("ghost :::= data\nsafe:\n\t@true\n")
    assert [task.name for task in app.list_tasks()] == ["safe"]


def test_unterminated_define_or_conditional_fails_closed(repo):
    from makefile_mcp.app import build_application
    from makefile_mcp.errors import MakeInspectionError

    root = repo("define VALUE\nghost:\n")
    with pytest.raises(MakeInspectionError, match="unterminated define"):
        build_application(root).list_tasks()

    (root / "Makefile").write_text("ifeq (1,1)\nghost:\n", encoding="utf-8")
    with pytest.raises(MakeInspectionError, match="unterminated conditional"):
        build_application(root).list_tasks()


def test_top_level_non_rule_constructs_with_colons_are_never_discovered(app_for):
    app = app_for(
        "vpath %.c src:generated\n"
        "$(info note: hello)\n"
        "$(warning caution: hello)\n"
        "export EXPORTED:VALUE\n"
        "unexport HIDDEN:VALUE\n"
        "undefine OLD:VALUE\n"
        "safe: ## Description: still a real target\n"
        "\t@true\n"
    )

    assert [task.name for task in app.list_tasks()] == ["safe"]
    assert app.describe_task("safe").description == "Description: still a real target"


def test_phantom_vpath_target_cannot_become_callable_via_implicit_rule(repo):
    root = repo("vpath %.c src:generated\nsafe:\n\t@true\n")
    # GNU Make could build `src` through an implicit rule when src.c exists,
    # but Makefile MCP must not authorize it unless an actual supported rule
    # declaration exposed that name.
    (root / "src.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")

    from makefile_mcp.app import build_application

    app = build_application(root)
    assert [task.name for task in app.list_tasks()] == ["safe"]
    with pytest.raises(TaskNotFound):
        app.describe_task("src")


def test_phony_inline_recipe_text_is_not_discovered_as_targets(repo):
    root = repo(".PHONY: safe; echo PHANTOM:VALUE\nsafe:\n\t@true\n")
    # If the parser exposed `printf`, GNU Make could satisfy it through a built-in implicit
    # compilation rule when printf.c exists. Inline recipe text must remain entirely non-callable.
    (root / "echo.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")

    from makefile_mcp.app import build_application

    app = build_application(root)
    assert [task.name for task in app.list_tasks()] == ["safe"]
    with pytest.raises(TaskNotFound):
        app.describe_task("echo")
    with pytest.raises(TaskNotFound):
        app.describe_task("PHANTOM:VALUE")
