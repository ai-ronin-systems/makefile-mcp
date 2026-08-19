# Development

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest
```

Useful project targets:

```bash
make check
make package
make docker-build
```

## Where changes go

- data/config contract: `models.py`
- expected public error: `errors.py`
- task exposure/discovery/context behavior: `core/catalog.py`
- variable or execution policy: `core/execution.py`
- diagnostics: `core/doctor.py`
- OS/Make/subprocess details: `infrastructure/`
- CLI-only rendering/parsing: `cli.py`
- MCP schema/tool wiring: `mcp_server.py`
- construction: `app.py`

Do not create a new abstraction merely to avoid importing a concrete function. Add a protocol only when there is a meaningful replaceable boundary or test seam. Do not add `utils.py`, `helpers.py`, generic managers, service locators, plugin managers, workflow engines, or command DSLs.

## Tests

Tests are grouped by behavior rather than implementation class:

- `tests/unit`: configuration, catalog/context, variables, capabilities and dependency rules;
- `tests/integration`: real Make execution, cache/context behavior, doctor and MCP;
- `tests/security`: execution and locking regressions.

For boundary changes, add a regression that proves the unsafe input is rejected or the resource limit is enforced.
