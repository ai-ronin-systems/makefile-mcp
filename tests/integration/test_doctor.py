def test_doctor_warns_for_dangerous_public_task(app_for):
    app = app_for(
        ".PHONY: destroy\ndestroy: ## Destroy\n\t@true\n",
        "schema_version: 1\ntasks:\n  destroy:\n    risk: dangerous\n",
    )
    result = app.doctor()
    assert result.ok
    assert any(f.code == "task.dangerous_public" for f in result.findings)
