# Contributing

Keep changes aligned with the product sentence:

> Make MCP discovers allowed Make targets, validates structured requests, runs Make without a shell, and returns structured results over CLI or MCP.

Before opening a change:

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest
```

Keep CLI/MCP thin, keep recipes in Make, add security regression coverage for boundary changes, and add abstractions only for real replaceable boundaries. See `docs/development.md`.
