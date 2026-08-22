# Just Make It MCP

**Expose trusted GNU Make targets to AI agents — without exposing a generic shell or replacing Make with another workflow system.**

Just Make It MCP (**JMIM**) turns an existing Makefile into typed MCP tools. It is **zero-config by default** for trusted local use and **deny-by-default when governed**.

```text
Makefile  →  JMIM  →  Codex / Claude / LangChain / Cursor / VS Code / MCP client
```

## Quick start

```bash
pipx install make-mcp        # or: uv tool install make-mcp
make-mcp serve
```

Given:

```make
test: ## Run tests
	pytest -q

lint: ## Run lint
	ruff check .
```

JMIM exposes `make_test` and `make_lint` as MCP tools.

```bash
make-mcp list
make-mcp doctor
make-mcp run test
make-mcp run test --preview   # GNU Make --dry-run; not a sandbox
```

One-shot use: `uvx make-mcp serve`.

## Features and advantages

| Area                | Feature / advantage                                          |
| ------------------- | ------------------------------------------------------------ |
| **Security**        | **No arbitrary shell/command tool.** Agents invoke exposed Make targets, not arbitrary host commands. |
| **Security**        | **GNU Make is treated as an interpreter boundary.** JMIM does not assume `shell=False` alone makes caller input safe. |
| **Security**        | **Typed governed inputs.** `token`, `enum`, `integer`, `boolean`, `path`, and `string` give caller input an explicit contract. |
| **Security**        | **Arbitrary strings stay out of Make assignment syntax.** They travel through a private JSON side channel instead of `NAME=<untrusted text>`. |
| **Security**        | **Repository confinement.** Contexts and `path` inputs stay inside the repository after symlink resolution. |
| **Security**        | **Make control variables are protected.** Names such as `SHELL`, `MAKEFLAGS`, `MAKEFILES`, `VPATH`, and `MAKE_MCP_INPUT` cannot be exposed as caller inputs. |
| **Security**        | **Governed mode is deny-by-default.** Only explicitly authorized `(context, target)` pairs are callable; changed policy fails closed until restart. |
| **Security**        | **Conservative static discovery.** Ambiguous Make syntax is omitted rather than guessed, reducing accidental tool exposure. |
| **Security**        | **Exact Makefile execution.** JMIM executes the same conventional top-level `Makefile` it inspected, via `make -f`. |
| **Runtime**         | **Bounded execution.** Input size, stdout, stderr, MCP error diagnostics, timeouts, and final pipe draining are bounded. |
| **Runtime**         | **MCP stdin cannot leak into recipes.** Child stdin is `/dev/null`. |
| **Runtime**         | **Process lifecycle is controlled.** Timeout/cancellation kills the task process group; same-group background descendants are cleaned up. |
| **Runtime**         | **Cross-process locking.** One active task per resolved physical context directory prevents alias-based concurrent writes. |
| **MCP**             | **Direct tools.** One typed MCP tool per authorized `(context, target)` pair gives agents strong discoverability and schemas. |
| **MCP**             | **Generic tools.** `list_tasks`, `describe_task`, and `run_task` provide a stable vocabulary for orchestrators and large catalogs. |
| **MCP**             | **One enforcement path.** Direct, generic, CLI, preview, contexts, and capabilities all use the same catalog, authorization, validator, and executor. |
| **MCP**             | **Correct error semantics.** Authorization, validation, timeout, and Make failures surface as MCP tool errors. |
| **MCP**             | **Progress/completion feedback.** Clients requesting progress receive truthful start/completion/failure events, not invented percentages. |
| **Execution**       | **Preview mode.** `--preview` / `preview=true` uses GNU Make `--dry-run` through the same policy and resource controls. |
| **Governance**      | **Zero-config auto mode.** Existing Makefiles work immediately for trusted local use; no YAML is required. |
| **Governance**      | **Optional explicit governance.** `.make-mcp.yaml` adds target exposure, typed inputs, risk metadata, contexts, capabilities, environment policy, and limits without defining commands. |
| **Monorepos**       | **Contexts.** Different repository directories get independent discovery, authorization, working directories, Makefiles, and locks. |
| **Orchestration**   | **Capabilities.** Stable semantic names such as `verify` or `appsec_scan` map to already-authorized Make targets without a plugin or workflow layer. |
| **Live use**        | **Catalog refresh.** Supported Makefile/include changes refresh discovery; authorization policy remains startup-stable and fail-closed. |
| **Diagnostics**     | **`doctor`.** Detects Make/runtime problems, exposure/configuration inconsistencies, missing targets, context aliasing, and unsafe operating assumptions. |
| **Integration**     | **Framework-neutral stdio MCP.** The same `make-mcp` server works with Codex, Claude, LangChain/LangGraph, Cursor, VS Code, and other MCP clients. |
| **Design**          | **Make remains the source of truth.** No duplicate workflow DSL, plugin command language, scheduler, database, or second execution engine. |
| **Design**          | **Small, auditable core.** Thin adapters sit around one application/catalog/executor path. |
| **Distribution**    | **Simple installation.** Use `pipx`, `uv tool`, or `uvx`; JMIM does not need to be embedded into the target repository. |
| **Release quality** | **Serious OSS release pipeline.** Multi-Python Linux/macOS CI, package smoke tests, PyPI Trusted Publishing, artifact validation, and provenance attestation. |

## Architecture

```text
                         Makefile
                            |
                    conservative catalog
                            |
              +-------------+-------------+
              |                           |
            auto                       governed
         no config                   .make-mcp.yaml
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

Without `.make-mcp.yaml`, JMIM runs in **auto mode**: every conservatively discovered root target is callable, with no caller-controlled Make variables.

Add `.make-mcp.yaml` to switch to explicit governance:

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

Just Make It MCP (JMIM) supports three MCP presentations over the same callable catalog. Choose the flavor which meets best your requirements.

```bash
make-mcp serve --tools direct    # default: one typed tool per callable target
make-mcp serve --tools generic   # list_tasks / describe_task / run_task
make-mcp serve --tools both      # both views, same execution core
```

See [MCP presentations](docs/mcp_presentations.md) and [client setup](docs/clients.md).

## Security

JMIM is a **constrained execution boundary around trusted repository automation**, not a sandbox for hostile Makefiles. Its model covers both OS subprocess behavior and GNU Make's own interpreter semantics, with explicit authorization, typed inputs, path confinement, resource bounds, process-group cleanup, and physical-context locking.

The built-in MCP server is **stdio-only**: no HTTP listener, remote-auth layer, TLS, tenancy, or network-service lifecycle is hidden inside the product.

See **[SECURITY.md](SECURITY.md)** for the security policy, reporting process, trust boundary, and limitations. Detailed implementation notes are in [docs/security.md](docs/security.md).

## Intentional scope limits

- GNU Make on **Linux/macOS**; Windows is not currently supported.
- **Trusted repository** assumption: Makefiles, includes, scripts, and provisioned tools are operator-controlled code.
- Static discovery is deliberately conservative, not a complete GNU Make parser.
- Preview is GNU Make dry-run, **not sandboxing**; Make evaluation can still have side effects.
- Direct tool inventory is registered at startup; generic catalog calls can observe supported Makefile changes.
- `.make-mcp.yaml` is startup policy; changes require restart and fail closed until then.
- Foreground/bounded tasks only; deliberately detached daemons are outside JMIM's process-group containment model.
- No HTTP server, auth stack, scheduler, job queue, workflow persistence, plugin execution framework, or arbitrary shell tool.
- Reload behavior: 
  - `.make-mcp.yaml` is startup policy. Restart JMIM after adding, removing, or editing it.
  - Makefile discovery refreshes when the conventional `Makefile` or tracked literal includes change.
  - Generic calls see the refreshed catalog immediately.
  - Direct tool inventory is a startup snapshot: adding or removing direct tools requires a restart. Existing direct tools still re-check the live catalog when invoked.

## Requirements

Python 3.11+ · GNU Make · Linux or macOS

## Documentation

1. [**Architecture**](docs/architecture.md) — runtime flow, responsibilities, lifecycle, invariants, and dependency rules.
2. [**CLI reference**](docs/cli.md) — commands, options, result model, root detection, and exit codes.
3. [**Configuration**](docs/configuration.md) — authoritative `.make-mcp.yaml` fields, defaults, and precedence.
4. [**Static Make discovery**](docs/discovery.md) — supported syntax, fail-closed behavior, includes, limitations, and cache semantics.
5. [**Governed mode**](docs/governed_mode.md) — explicit exposure, typed inputs, risk metadata, and operating model.
6. [**MCP presentations**](docs/mcp_presentations.md) — `direct`, `generic`, `both`, schemas, result/error semantics, naming, and lifecycle.
7. [**Contexts and capabilities**](docs/contexts_and_capabilities.md) — monorepo scoping, `(context, target)` authorization, and semantic mappings.
8. [**MCP client setup**](docs/clients.md) — Codex, Claude Code, LangChain/LangGraph, Cursor, VS Code, and `uvx` examples.
9. [**Security**](docs/security.md) — trust boundary, Make input safety, arbitrary strings, discovery, environment/path controls, and execution bounds.
10. [**Development**](docs/development.md) — contributor workflows, code ownership, regression expectations, and Definition of Done.
11. [**Deployment**](docs/deployment.md) — Docker/stdio deployment, production checklist, and provisioning custom tools plus Makefiles.
12. [**AuditHound integration pattern**](docs/integrations/audithound.md) — orchestration/evidence-provider integration guidance.
13. [**Releasing**](docs/releasing.md) — version/tag contract, clean-package smoke test, PyPI Trusted Publishing, provenance, and GitHub Releases.

Security reporting: [SECURITY.md](SECURITY.md).
Contributing: [CONTRIBUTING.md](CONTRIBUTING.md).
