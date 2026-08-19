def test_capability_is_simple_mapping(app_for):
    app = app_for(
        ".PHONY: test\ntest: ## Test\n\t@true\n",
        "schema_version: 1\ncapabilities:\n  verify: test\n",
    )
    assert app.resolve_capability("verify").name == "test"
