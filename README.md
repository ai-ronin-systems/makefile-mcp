# Make MCP

Make MCP exposes **explicitly allowed Make targets** as structured CLI operations and MCP tools. Make remains authoritative for recipes, dependencies, ordering and project-specific workflow; Make MCP adds discovery, exposure metadata, typed inputs, repository confinement, bounded execution, locking and stable results.

> If Make can already express it, Make MCP does not model it again.

## Install

```bash
pipx install .
# or
uv tool install .
```

Requires Python 3.11+ and GNU Make.

## Quick start

A normal Makefile is enough:

```make
.PHONY: test
test: ## Run tests
	pytest -q
```

Optional `.make-mcp.yaml` adds metadata only:

```yaml
schema_version: 1

defaults:
  timeout_seconds: 600

tasks:
  test:
    variables:
      MODULE:
        type: string

capabilities:
  verify: test
```

Then:

```bash
make-mcp list
make-mcp describe test
make-mcp run test MODULE=security
make-mcp doctor
make-mcp serve
```

Only enabled configured tasks, documented `##` targets and explicit `.PHONY` targets are exposed. Merely discovering a target never authorizes execution.

## MCP

`make-mcp serve` starts a stdio server exposing exactly:

- `list_tasks`
- `describe_task`
- `run_task`

MCP is a thin interface; task policy and execution live in protocol-independent code.

## Architecture

The implementation deliberately avoids structural ceremony:

```text
CLI / MCP
   ↓
Application facade
   ↓
Catalog | Execution | Doctor
   ↓
Make | Filesystem | Subprocess
```

See [Architecture](docs/architecture.md), [Configuration](docs/configuration.md), [Security](docs/security.md), [Development](docs/development.md), and [Design decisions](docs/design-decisions.md).

## Docker

```bash
docker build -t make-mcp:local .

docker run --rm -i \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  -w /workspace \
  make-mcp:local serve
```

Or:

```bash
docker compose run --rm make-mcp doctor
```

## Security summary

- no arbitrary shell tool or command field in YAML;
- execution uses argv and never `shell=True`;
- only declared variables are accepted;
- path variables and contexts are confined after symlink resolution;
- stdout/stderr are bounded while pipes are fully drained;
- timeout/cancellation terminates the process group;
- one active task per context uses a cross-process file lock;
- child environment is explicitly inherited/allowed.

See `SECURITY.md` and `docs/security.md`.

## Development

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest
```

## Non-goals

No workflow engine, scheduler, LLM, database, cloud service, authentication layer, plugin framework, package-manager abstraction, CI abstraction, container abstraction, command DSL or framework-specific result parser.

## License

MIT.
