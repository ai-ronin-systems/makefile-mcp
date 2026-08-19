import pytest

from make_mcp.errors import TaskNotExposed


def test_exposure_precedence_and_private_target(app_for):
    app = app_for(
        ".PHONY: phony\n"
        "documented: ## Public docs\n\t@true\n"
        "phony:\n\t@true\n"
        "private:\n\t@true\n"
        "configured:\n\t@true\n",
        "schema_version: 1\ntasks:\n  configured:\n    risk: write\n",
    )
    tasks = {task.name: task for task in app.list_tasks()}
    assert set(tasks) == {"configured", "documented", "phony"}
    assert tasks["configured"].exposure_source == "config"
    assert tasks["configured"].risk == "write"
    with pytest.raises(TaskNotExposed):
        app.describe_task("private")


def test_disabled_target_stays_hidden(app_for):
    app = app_for(
        ".PHONY: deploy\ndeploy: ## Deploy\n\t@true\n",
        "schema_version: 1\ntasks:\n  deploy:\n    enabled: false\n",
    )
    assert app.list_tasks() == []
    with pytest.raises(TaskNotExposed):
        app.describe_task("deploy")
