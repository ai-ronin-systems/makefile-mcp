# Contributing

Keep changes aligned with the product boundary:

> Makefile MCP exposes trusted Make targets to MCP clients with zero-config discovery or explicit governed policy, while preserving one bounded execution path.

The repository Makefile is the contributor interface:

```bash
make install
make check
```

Keep CLI/MCP adapters thin, keep recipes in Make, add regressions for boundary changes, and add abstractions only when a concrete second implementation or distinct responsibility justifies them.

See [docs/development.md](docs/development.md) for contributor workflows, ownership boundaries, regression expectations, and Definition of Done. Public contracts are documented in the [CLI reference](docs/cli.md), [configuration reference](docs/configuration.md), and [static discovery contract](docs/discovery.md).

Release maintainers should also follow [docs/releasing.md](docs/releasing.md); PyPI artifacts are published only by the tag-driven GitHub Actions workflow.
