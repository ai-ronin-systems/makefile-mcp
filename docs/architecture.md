# Architecture

Just Make It MCP (JMIM) is intentionally small: one callable catalog, one execution path, and thin CLI/MCP presentations.

## Two independent dimensions

```text
Exposure policy                  MCP presentation
---------------                  ----------------
no .make-mcp.yaml -> auto        direct | generic | both
.make-mcp.yaml    -> governed
```

Exposure controls **what may run**. Presentation controls **how MCP clients see it**. Neither creates a second executor.

## Runtime flow

```text
                         Makefile
                            |
                    StaticMakeInspector
                            |
                          Catalog
                            |
                auto / governed exposure
                            |
                       Application
                 +----------+----------+
                 |                     |
               CLI                    MCP
                                +------+------+
                                |             |
                             direct        generic
                                |             |
                                +------+------+
                                       |
                                  TaskExecutor
                                  /    |     \
                            Inputs   Lock   Process
                                       |
                                  make -f exact
                                    Makefile
```

## Source layout

```text
src/make_mcp/
├── app.py          # composition root + protocol-independent application facade
├── catalog.py      # contexts, discovery cache, exposure policy, capabilities
├── cli.py          # Typer adapter
├── config.py       # optional .make-mcp.yaml loading + exposure-mode decision
├── doctor.py       # read-only diagnostics
├── errors.py       # expected public errors
├── execution.py    # authorized execution orchestration
├── filesystem.py   # root/path/fingerprint/lock filesystem primitives
├── inputs.py       # input validation + arbitrary-string JSON lifecycle
├── makefile.py     # conservative static Makefile inspection
├── models.py       # configuration and runtime contracts
├── process.py      # bounded subprocess/process-tree lifecycle
├── syntax.py       # shared Make/MCP lexical and boolean rules
├── version.py      # single package-version source
└── mcp/            # protocol-specific presentation boundary
    ├── __init__.py
    ├── presentation.py  # direct-tool name/signature/delegate derivation
    └── server.py        # MCP SDK registration and transport
```

The package stays flat for application responsibilities. The only subpackage is `mcp/`, because
protocol presentation is a real external boundary with two cohesive modules. There is deliberately
no `core/`/`infrastructure/` split, ports package, DI framework, service locator, plugin system,
workflow engine, or use-case-per-file hierarchy.

## Responsibility boundaries

SRP is applied at module scale:

- `catalog.py` owns callable discovery/exposure state;
- `inputs.py` owns caller-input validation, normalization, and JSON string transport;
- `execution.py` owns orchestration from authorized task to normalized result;
- `mcp/presentation.py` owns direct MCP presentation derivation and contains no MCP SDK dependency;
- `mcp/server.py` owns MCP SDK registration and stdio transport only;
- `syntax.py` is the single authority for lexical rules shared by config, inputs, and direct schemas;
- `process.py` is the only module that creates subprocesses;
- `makefile.py` inspects Make syntax but never evaluates recipes;
- `filesystem.py` keeps the small related filesystem primitives together rather than splitting them into ceremony modules;
- `models.py` remains a single contracts module while the project is small enough for that to stay cohesive.

## Exposure architecture

### Auto

When `.make-mcp.yaml` is absent, every conservatively discovered root target becomes callable. Tasks are parameterless and use default limits/risk metadata.

### Governed

When `.make-mcp.yaml` exists, exposure is deny-by-default. A target must both exist in conservative discovery and be explicitly enabled for the selected context.

The authorization unit is `(context, target)`. Configuration never contains recipes or executable command DSLs.

See [Governed mode](governed_mode.md).

## MCP presentation architecture

### Direct

At server creation, JMIM snapshots the callable catalog and derives one tool per `(context, target)`. Governed variable contracts become tool schemas. Generated callables are thin delegates to `Application.run_task()`. The optional `preview` control follows the same path and only changes the final GNU Make argv by adding `--dry-run`. MCP progress remains adapter-only and does not enter the application/executor layers.

### Generic

The stable `list_tasks`, `describe_task`, and `run_task` operations query the application/catalog at call time.

### Both

Registers both presentations without duplicating policy or execution code.

See [MCP presentations](mcp_presentations.md).

## Input/execution boundary

```text
constrained scalar
  -> validate/normalize
  -> NAME=value
  -> make -f Makefile target

arbitrary string
  -> private bounded JSON
  -> generated MAKE_MCP_INPUT path
  -> make -f Makefile target
```

The executor pins the exact Makefile used for discovery. Process creation, output retention, timeouts, cancellation, and process-tree cleanup are centralized in `process.py`.

See [Security](security.md) for the threat model.

## Lifecycle and caching

`.make-mcp.yaml` presence and contents are resolved in one configuration-load operation per `Application` lifetime. The startup fingerprint is checked on subsequent operations; any policy-file appearance, removal, or modification fails closed and requires restart rather than being hot-reloaded.

Catalog discovery is cached per context. The cache fingerprints lexical and resolved Makefile/include identities plus lightweight filesystem metadata, including missing optional literal include paths. Ordinary edits, inode changes, and include-symlink retargeting therefore invalidate the snapshot without hashing repository files on every call.

Generic APIs observe refreshed catalog state at call time. Direct tool inventory is a server-startup snapshot, but every invocation re-authorizes through the live catalog before execution.

## Dependency rules

- contracts/errors do not depend on CLI, MCP, or process execution;
- `mcp/presentation.py` does not import the MCP SDK;
- CLI and MCP adapters delegate to `Application`;
- only `process.py` creates raw subprocesses;
- Make recipes are never represented in Python/YAML;
- configuration does not define commands, pipelines, or dependencies;
- one implementation does not justify a protocol/adapter hierarchy by itself.

Architecture tests enforce these boundaries and forbid obsolete package layers and patch-delivery artifacts in the product tree.

## Architecture invariants

These are code-level contracts, not aspirations. Architecture tests protect the dependency boundaries and execution ownership behind them.

1. **Make owns commands and workflow.** Recipes, dependencies, ordering, and tool invocation stay in Makefiles.
2. **All callable execution passes through `TaskExecutor`.** CLI, direct MCP, generic MCP, and preview cannot create parallel execution paths.
3. **Only `process.py` creates subprocesses.** Adapters and policy layers do not launch commands.
4. **Governed authorization identity is `(context, target)`.** Names alone are not global permissions.
5. **Arbitrary strings never become GNU Make command-line assignments.** They use the private JSON data channel.
6. **Presentation cannot widen authorization.** MCP schemas improve client UX; live application authorization remains authoritative.
7. **Policy is startup-stable.** `.make-mcp.yaml` changes fail closed and require restart rather than being hot-reloaded.
8. **Direct inventory may be stale; direct authorization may not.** Tool registration is a startup snapshot, but every invocation re-enters the live catalog.

See [Static Make discovery](discovery.md) for the non-evaluating inventory contract and [CLI reference](cli.md) for the public command surface.

## Design constraints

1. Make remains authoritative for commands, dependencies, ordering, and workflow.
2. Auto mode is zero-config and parameterless.
3. Governed mode is explicit `(context, target)` authorization with declared inputs only.
4. Arbitrary strings never cross GNU Make as arbitrary variable values.
5. Direct/generic/both are presentations of one application policy and one executor.
6. Risk metadata is advisory and defaults to `unknown`.
7. Stdio is the built-in MCP transport; network auth is not invented around a non-network server.
8. POSIX assumptions are explicit rather than hidden behind portability abstractions.
9. New abstractions require a real second implementation, proven test seam, or distinct responsibility.
