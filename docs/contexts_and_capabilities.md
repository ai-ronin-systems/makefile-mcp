# Contexts and capabilities

Contexts and capabilities let Just Make It MCP (JMIM) scale beyond a single root Makefile without introducing another execution model.

They solve different problems:

- **contexts** scope discovery, authorization, and execution to a repository directory;
- **capabilities** give orchestrators stable semantic names for already-authorized Make targets.

Neither feature creates commands. GNU Make remains the execution engine and the Makefile remains the source of truth.

## Mental model

```text
repository
├── Makefile
├── backend/
│   └── Makefile
└── frontend/
    └── Makefile

JMIM policy
├── context: root      -> ./
├── context: backend   -> ./backend
├── context: frontend  -> ./frontend
│
├── authorized task: backend:test
├── authorized task: frontend:test
└── capability: verify -> test
```

The effective authorization unit is always:

```text
(context, target)
```

A target named `test` in two contexts represents two distinct callable operations. A capability such as `verify -> test` resolves only where `test` is already callable.

## Contexts

A context names a repository-confined directory containing its own conventional `Makefile`.

```yaml
schema_version: 1

contexts:
  backend:
    directory: backend
  frontend:
    directory: frontend
```

`root` is built in and always refers to the detected repository root. It is reserved and must not be redefined.

Configured context directories are resolved after symlink resolution and must remain at or below the repository root. They must exist and be directories.

### Context-scoped discovery

Each context is inspected independently from its own conventional `Makefile`:

```text
root      -> ./Makefile
backend   -> ./backend/Makefile
frontend  -> ./frontend/Makefile
```

Literal Makefile includes tracked by the inspector belong to that context's discovery snapshot. Supported Makefile changes invalidate that context's catalog independently; `.make-mcp.yaml` remains startup policy and requires a restart when changed.

### Context-scoped authorization

In governed mode, a task must be both:

1. discovered in the selected context; and
2. explicitly enabled for that context.

```yaml
tasks:
  test:
    contexts: [backend, frontend]

  deploy:
    contexts: [backend]
    risk: dangerous
```

This exposes:

```text
backend:test
frontend:test
backend:deploy
```

It does not expose `root:test`, `root:deploy`, or `frontend:deploy` merely because a target with the same name exists there.

A task entry never creates a Make target. If the configured target is not discovered in a declared context, `make-mcp doctor` reports an error.

### Context-scoped execution

The selected context controls all of the following:

- the directory inspected for the top-level `Makefile`;
- the authorized task catalog;
- the execution working directory;
- the exact top-level Makefile passed to `make -f`;
- the execution lock.

JMIM permits at most one active task per resolved physical context directory through its cross-process lock. Distinct context names that resolve to the same directory therefore share a lock, and `doctor` reports that aliasing as a configuration error. Genuinely different context directories have independent locks.

### Direct MCP naming

In direct presentation, each authorized `(context, target)` pair becomes a distinct MCP tool.

```text
root:test       -> make_test
backend:test    -> make_backend_test
frontend:test   -> make_frontend_test
```

Generated MCP names are presentation metadata. Execution retains the original context and target even when a name must be sanitized or disambiguated.

See [MCP presentations](mcp_presentations.md) for naming and lifecycle details.

## Capabilities

A capability is a semantic name mapped to a concrete Make target name.

```yaml
capabilities:
  verify: test
  package: build
  appsec_scan: scan-appsec
```

Capabilities are useful when an orchestrator should depend on intent such as `verify` or `package`, while repositories remain free to express the implementation as ordinary Make targets.

The mapping is deliberately small:

```text
semantic capability -> Make target
```

It is not a workflow, alias language, dependency graph, or alternate execution engine.

### Capabilities are context-scoped views

Capability configuration is repository-wide, but resolution is context-scoped because the mapped target must be callable in the requested context.

Given:

```yaml
contexts:
  backend:
    directory: backend
  frontend:
    directory: frontend

tasks:
  test:
    contexts: [backend]

capabilities:
  verify: test
```

then:

```text
backend:  verify -> test   available
frontend: verify -> test   unavailable
```

`list_tasks` in generic MCP presentation reports only capability mappings whose targets are callable in the requested context.

A capability cannot expose a hidden target, bypass task policy, alter variables, change risk metadata, or override execution limits. Resolution ends at the same authorized `TaskDefinition` used by normal task execution.

### Capabilities are not executable aliases

Capabilities are semantic discovery/lookup metadata, not a second executable namespace.

JMIM does not create direct MCP tools named after capabilities, and generic `run_task` executes a target name. An orchestrator can discover a capability mapping, resolve it to its authorized target for the selected context, and invoke that target through the normal execution path.

This keeps authorization and execution centered on one identity:

```text
(context, target)
```

rather than maintaining parallel task and capability execution models.

## Monorepo example

```yaml
schema_version: 1

contexts:
  api:
    directory: services/api
  web:
    directory: services/web

tasks:
  test:
    contexts: [api, web]
    risk: safe

  lint:
    contexts: [api, web]
    risk: safe

  build:
    contexts: [web]
    risk: write

capabilities:
  verify: test
  quality: lint
  package: build
```

The callable surface is:

```text
api:test
api:lint
web:test
web:lint
web:build
```

The context-valid capability views are:

```text
api:
  verify  -> test
  quality -> lint

web:
  verify  -> test
  quality -> lint
  package -> build
```

The Makefiles still own recipes, dependencies, ordering, and tool invocation. JMIM adds naming, scope, authorization, validation, and bounded execution around that existing surface.

## Choosing contexts

Use contexts when a repository has distinct Makefile roots that should be independently discoverable and governable, for example:

- monorepo services;
- frontend and backend subprojects;
- infrastructure separated from application code;
- independent evidence/tooling directories.

Do not create contexts merely to group targets conceptually. A context has operational meaning: it changes the Makefile, working directory, authorization scope, and lock domain.

## Choosing capabilities

Use capabilities when a caller should depend on stable intent rather than repository-specific target naming.

Good examples:

```text
verify
package
appsec_scan
quality
```

Avoid using capabilities as aliases for every target. If callers can depend directly on the Make target name, an extra semantic mapping adds no value.

## Related documentation

- [Governed mode](governed_mode.md) — deny-by-default exposure and the governed operating model.
- [Configuration](configuration.md) — exact YAML schema for contexts, tasks, and capabilities.
- [MCP presentations](mcp_presentations.md) — how context-scoped tasks appear in direct and generic MCP.
- [Security](security.md) — repository confinement, authorization, input handling, and execution boundaries.
- [Architecture](architecture.md) — catalog, application, executor, and lifecycle design.

See also [Static Make discovery](discovery.md) for context-local inventory semantics.
