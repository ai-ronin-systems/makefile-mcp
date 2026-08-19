# Architecture

Make MCP is deliberately small:

```text
CLI ─┐
     ├─> Application facade ─> Catalog / Execution / Doctor
MCP ─┘                         │
                               └─> Make / filesystem / subprocess boundaries
```

Source layout:

```text
src/make_mcp/
├── app.py                    # composition root + application facade
├── cli.py                    # Typer interface
├── mcp_server.py             # MCP stdio interface
├── models.py                 # stable data/config contracts
├── errors.py                 # expected public errors
├── config.py                 # .make-mcp.yaml loader
├── core/
│   ├── catalog.py            # contexts, discovery merge, exposure, cache
│   ├── execution.py          # variables, argv/env, execution orchestration
│   └── doctor.py             # read-only diagnostics
└── infrastructure/
    ├── make.py               # static Makefile inspection
    ├── filesystem.py         # roots, confinement, fingerprints, file locks
    └── process.py            # bounded subprocess/process-tree lifecycle
```

There is no ports package, use-case-per-file hierarchy, DI framework, service locator, or plugin system. `ProcessRunner` and `ContextLock` remain protocols inside `core/execution.py` because process execution and cross-process locking are genuine replaceable safety boundaries.

## Dependency rules

- `models.py` and `errors.py` do not depend on CLI, MCP, YAML, or infrastructure.
- `core/` does not depend on Typer or MCP.
- `cli.py` and `mcp_server.py` are thin adapters over `Application`.
- raw subprocess creation exists only in `infrastructure/process.py`.
- Make recipes are never represented in Python or YAML.

These rules are covered by architecture tests.

## Discovery and authorization

Discovery is intentionally broader than authorization. The catalog exposes, in order of precedence:

1. enabled tasks explicitly present in `.make-mcp.yaml`;
2. targets carrying `##` documentation;
3. explicit `.PHONY` targets.

Other discovered targets remain non-executable diagnostics. A target existing in a Makefile is not enough to authorize it.

Discovery is static: normal rules, `.PHONY`, `##` comments and literal includes are parsed without executing Make. Dynamic includes produce doctor warnings.
