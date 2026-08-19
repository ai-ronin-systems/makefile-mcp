# Makefile MCP

<!-- mcp-name: io.github.ai-ronin-systems/makefile-mcp -->

**Expose trusted GNU Make targets to AI agents — without exposing a generic shell or replacing Make with another workflow system.**

Makefile MCP turns an existing Makefile into typed MCP tools. It is **zero-config by default** for trusted local use and **deny-by-default when governed**.

```text
Makefile  →  Makefile MCP  →  Codex / Claude / LangChain / Cursor / VS Code / MCP client
```

## Quick start

```bash
pipx install makefile-mcp        # or: uv tool install makefile-mcp
makefile-mcp serve
```

Given:

```make
test: ## Run tests
	pytest -q

lint: ## Run lint
	ruff check .
```

Makefile MCP exposes `make_test` and `make_lint` as MCP tools.

```bash
makefile-mcp list
makefile-mcp doctor
makefile-mcp run test
makefile-mcp run test --preview   # GNU Make --dry-run; not a sandbox
```

One-shot use: `uvx makefile-mcp serve`.

## Why Makefile MCP

Makefile MCP is intentionally narrow: the repository's Makefile remains the executable source of truth, while Makefile MCP supplies a governed agent-facing capability boundary.

| Principle | What it means |
| --- | --- |
| **Make stays authoritative** | No duplicate workflow DSL, plugin command language, scheduler, database, or second execution engine. |
| **No generic shell capability** | Agents invoke discovered or explicitly governed Make targets, not arbitrary host commands. |
| **Trusted Makefile, untrusted invocation** | Repository automation is trusted; caller-selected tasks and declared values are authorized, validated, and bounded. GNU Make's own variable/function semantics are treated as an interpreter boundary. |
| **One execution path** | CLI, direct MCP tools, generic MCP tools, preview, contexts, and capabilities share the same catalog, authorization, validation, and executor. |
| **Conservative discovery** | Makefile MCP statically exposes only Make syntax it can classify confidently; ambiguous constructs are omitted rather than guessed. |
| **Bounded Unix runtime** | Foreground execution has bounded input/output, timeout/cancellation cleanup, stdin isolation, process-group handling, and physical-context locking. |

See [Design rationale](docs/design_rationale.md) for the full capability/property map and the alternatives deliberately left out.

## Architecture

```text
                         Makefile
                            |
                    conservative catalog
                            |
              +-------------+-------------+
              |                           |
            auto                       governed
         no config                   .makefile-mcp.yaml
              |                           |
              +-------------+-------------+
                            |
                       Application
                  +---------+---------+
                  |                   |
              MCP direct         MCP generic
                  +---------+---------+
                            |
                         Executor
                            |
                      exact `make -f`
```

One catalog. One execution path. Thin CLI and MCP adapters.

See [Architecture](docs/architecture.md).

## Governed mode

Without `.makefile-mcp.yaml`, Makefile MCP runs in **auto mode**: every conservatively discovered root target is callable, with no caller-controlled Make variables.

Add `.makefile-mcp.yaml` to switch to explicit governance:

```yaml
schema_version: 1

contexts:
  backend:
    directory: backend

tasks:
  test:
    contexts: [root, backend]
    risk: safe

  deploy:
    risk: dangerous
    variables:
      ENV:
        type: enum
        values: [staging, production]
        required: true

capabilities:
  verify: test
```

Only enabled `(context, target)` pairs are callable. See [Governed mode](docs/governed_mode.md), [Configuration](docs/configuration.md), and [Contexts and capabilities](docs/contexts_and_capabilities.md).

## MCP presentations

Makefile MCP supports three MCP presentations over the same callable catalog. Choose the presentation that best fits your requirements.

```bash
makefile-mcp serve --tools direct    # default: one typed tool per callable target
makefile-mcp serve --tools generic   # list_tasks / describe_task / run_task
makefile-mcp serve --tools both      # both views, same execution core
```

See [MCP presentations](docs/mcp_presentations.md) and [client setup](docs/clients.md).

## Security

Makefile MCP assumes the repository, Makefiles, included Make code, wrapper scripts, and provisioned tools are **trusted operator-controlled code**. The security boundary is the invocation: an MCP/CLI caller chooses an exposed task/context and, in governed mode, supplies declared values. Makefile MCP authorizes and validates that request; it does **not** sandbox hostile Makefiles.

Runtime bounds, cancellation/process-group cleanup, stdin isolation, and locking are primarily execution-correctness properties. They limit failure modes around trusted automation rather than turning Make into a sandbox. The built-in MCP server is **stdio-only**: no HTTP listener, remote-auth layer, TLS, tenancy, or network-service lifecycle is hidden inside the product.

See **[SECURITY.md](SECURITY.md)** for the security policy, reporting process, trust boundary, and limitations. Detailed implementation notes are in [docs/security.md](docs/security.md).

## Intentional scope limits

- GNU Make on **Linux/macOS**; Windows is not currently supported.
- **Trusted repository** assumption: Makefiles, includes, scripts, and provisioned tools are operator-controlled code.
- Static discovery is deliberately conservative, not a complete GNU Make parser.
- Preview is GNU Make dry-run, **not sandboxing**; Make evaluation can still have side effects.
- Direct tool inventory is registered at startup; generic catalog calls can observe supported Makefile changes.
- `.makefile-mcp.yaml` is startup policy; changes require restart and fail closed until then.
- Foreground/bounded tasks only; deliberately detached daemons are outside Makefile MCP's process-group containment model.
- No HTTP server, auth stack, scheduler, job queue, workflow persistence, plugin execution framework, or arbitrary shell tool.
- Reload behavior:
  - `.makefile-mcp.yaml` is startup policy. Restart Makefile MCP after adding, removing, or editing it.
  - Makefile discovery refreshes when the conventional `Makefile` or tracked literal includes change.
  - Generic calls see the refreshed catalog immediately.
  - Direct tool inventory is a startup snapshot: adding or removing direct tools requires a restart. Existing direct tools still re-check the live catalog when invoked.

## Requirements

Python 3.11+ · GNU Make · Linux or macOS

## Documentation

1. [**Architecture**](docs/architecture.md) — runtime flow, responsibilities, lifecycle, invariants, and dependency rules.
2. [**Design rationale**](docs/design_rationale.md) — key tradeoffs, full product-property map, and deliberately rejected alternatives.
3. [**CLI reference**](docs/cli.md) — commands, options, result model, root detection, and exit codes.
4. [**Configuration**](docs/configuration.md) — authoritative `.makefile-mcp.yaml` fields, defaults, and precedence.
5. [**Static Make discovery**](docs/discovery.md) — supported syntax, fail-closed behavior, includes, limitations, and cache semantics.
6. [**Governed mode**](docs/governed_mode.md) — explicit exposure, typed inputs, risk metadata, and operating model.
7. [**MCP presentations**](docs/mcp_presentations.md) — `direct`, `generic`, `both`, schemas, result/error semantics, naming, and lifecycle.
8. [**Contexts and capabilities**](docs/contexts_and_capabilities.md) — monorepo scoping, `(context, target)` authorization, and semantic mappings.
9. [**MCP client setup**](docs/clients.md) — Codex, Claude Code, LangChain/LangGraph, Cursor, VS Code, and `uvx` examples.
10. [**Security**](docs/security.md) — trust boundary, Make input safety, arbitrary strings, discovery, environment/path controls, and execution bounds.
11. [**Development**](docs/development.md) — contributor workflows, code ownership, regression expectations, and Definition of Done.
12. [**Deployment**](docs/deployment.md) — Docker/stdio deployment, production checklist, and provisioning custom tools plus Makefiles.
13. [**Releasing**](docs/releasing.md) — version/tag contract, clean-package smoke test, PyPI Trusted Publishing, provenance, GitHub Releases, and MCP Registry metadata.

Security reporting: [SECURITY.md](SECURITY.md).
Contributing: [CONTRIBUTING.md](CONTRIBUTING.md).
