# Development

This is the contributor engineering guide for Makefile MCP. The repository Makefile is the local contributor interface; `make help` is the authoritative command catalog.

Start with:

```bash
make install
make check
```

For release-sensitive changes also run:

```bash
make typecheck
make dependency-audit
make package
make package-smoke
```

`typecheck` and `dependency-audit` intentionally stay outside `make check`: both use separately exact-pinned tools, and dependency auditing requires live advisory/index access. CI and the release workflow run them as additional blocking gates.

## High-value developer commands

| Command | Use |
| --- | --- |
| `make install` | Sync the exact development environment. |
| `make check` | Format check, Ruff lint, branch-aware coverage gate, and `doctor`; deterministic local release gate. |
| `make typecheck` | Exact-pinned Pyright static analysis of `src/makefile_mcp`; CI/release gate, fetched separately from the locked project environment. |
| `make dependency-audit` | Export the frozen runtime dependency set and audit it with exact-pinned `pip-audit`; network-backed CI/release gate. |
| `make test-security` | Security and boundary regressions. |
| `make test-integration` | Real GNU Make/process/MCP integration behavior. |
| `make coverage` | Full branch-aware suite with the enforced 85% project floor. |
| `make test-one TEST=...` | Focus one test or node while iterating. |
| `make smoke` | CLI bootstrap, diagnostics, and discovery smoke. |
| `make package-smoke` | Exercise the built wheel over CLI/MCP stdio and smoke-install the sdist in a clean Linux container. |
| `make release-check TAG=vX.Y.Z` | Verify tag/version/changelog identity. |

Use `make help` rather than this document for the full list of utility, Docker, packaging, and maintenance targets.

## Code ownership map

| Concern | Module |
| --- | --- |
| application composition/facade | `app.py` |
| exposure, contexts, catalog cache, capabilities | `catalog.py` |
| CLI rendering/parsing | `cli.py` |
| optional policy loading | `config.py` |
| diagnostics | `doctor.py` |
| public domain errors | `errors.py` |
| authorized task transaction | `execution.py` |
| root/path/fingerprint/locking primitives | `filesystem.py` |
| typed input validation and string JSON transport | `inputs.py` |
| conservative static Make inspection | `makefile.py` |
| configuration/runtime contracts | `models.py` |
| subprocess/process-tree lifecycle | `process.py` |
| shared lexical/control rules | `syntax.py` |
| direct MCP schema/name derivation | `mcp/presentation.py` |
| MCP SDK registration/stdio transport | `mcp/server.py` |

Keep the package flat. Do not introduce generic managers, service locators, `utils.py`, plugin frameworks, workflow DSLs, or interface layers without a concrete second implementation or distinct responsibility.

## Architecture rules for changes

The canonical invariants live in [Architecture](architecture.md#architecture-invariants). In day-to-day work, preserve these practical rules:

- commands and dependencies stay in Makefiles;
- all execution continues through `TaskExecutor`;
- only `process.py` creates subprocesses;
- direct/generic/CLI adapters remain thin;
- configuration describes policy, not executable recipes;
- conservative discovery must never widen because a line merely *looks* like a rule;
- security validation may intentionally be repeated at separate trust boundaries.

## Changing static discovery

Read [Static Make discovery](discovery.md) first.

1. Reproduce the GNU Make construct in a minimal fixture.
2. Decide whether Makefile MCP can classify it **without evaluating Make semantics**.
3. Prefer omission/fail-closed behavior over a false-positive callable target.
4. Add a regression that checks the callable inventory.
5. When a false positive could become executable through an implicit rule, prove that the phantom name is not callable.
6. Exercise real GNU Make where its semantics are relevant; do not test only the Python regex/state machine.
7. Run at least `make test-security` and `make test-integration`.

Do not solve discovery completeness by invoking `make -qp` or another Make-evaluation path from discovery.

## Changing input transport or configuration

1. Update the Pydantic/runtime contract in `models.py` when public schema changes.
2. Keep lexical/control-name rules centralized in `syntax.py`.
3. Keep runtime caller validation in `inputs.py` even when MCP schemas already validate client input.
4. Preserve the distinction between Make-safe scalar assignments and arbitrary `string` data through `MAKEFILE_MCP_INPUT` JSON.
5. Verify direct MCP signatures still derive from the same `VariableSpec` contract.
6. Update [Configuration](configuration.md), [Security](security.md), and relevant examples when semantics change.

A new input type is justified only when it has a distinct validation/transport contract; do not create aliases for cosmetic naming.

## Changing execution or process behavior

1. Keep task orchestration in `TaskExecutor` and raw process lifecycle in `process.py`.
2. Preserve non-interactive stdin, bounded output, timeout/cancellation cleanup, and physical-context locking.
3. Add regression coverage for success, failure, timeout/cancellation, and cleanup behavior affected by the change.
4. Avoid background-job/supervisor abstractions; Makefile MCP tasks are foreground/bounded operations.
5. Re-run security and integration tests.

## Changing MCP presentation

1. Keep `mcp/presentation.py` independent from the MCP SDK.
2. Keep MCP-specific `Context`, progress, annotations, and transport registration in `mcp/server.py`.
3. Do not bypass `Application` for direct or generic execution.
4. Keep protocol errors at the adapter boundary; application/CLI code continues using domain errors and `TaskResult`.
5. Add/adjust real SDK integration tests in `tests/integration/test_mcp.py`.
6. Verify generated tool schemas do not expose SDK-injected context parameters.

See [MCP presentations](mcp_presentations.md) for the external contract.

## Test organization and expectations

- `tests/unit` — configuration, discovery, catalog/context behavior, variables, capabilities, CLI/presentation helpers, architecture, release/docs invariants;
- `tests/integration` — real Make execution, cache/context behavior, diagnostics, process lifecycle, MCP SDK integration;
- `tests/security` — interpreter/input/path/locking/resource-boundary regressions.

Boundary changes require a regression proving the unsafe/ambiguous case is rejected, omitted conservatively, or remains bounded. A green happy-path test alone is not enough for a security-sensitive boundary change. `PytestUnraisableExceptionWarning` is treated as an error so subprocess/resource cleanup regressions cannot pass as warning-only test runs.

### Coverage gate

`make coverage` runs the complete pytest suite under branch-aware `coverage.py` measurement and enforces an 85% project floor. `make check` uses that coverage run as its test gate, so local validation and CI exercise the same contract.

The threshold is deliberately below 100%: Makefile MCP prioritizes realistic security, process-lifecycle, Make-semantics, and public-contract tests over mocking platform race/fallback branches solely to increase a metric. New behavior should add the closest meaningful regression rather than target a percentage mechanically.

## Definition of Done

For behavior-changing work:

- [ ] the change stays within an existing responsibility boundary, or a new abstraction has a concrete justification;
- [ ] no parallel command/execution path was introduced;
- [ ] authorization and trust-boundary impact were considered;
- [ ] regression coverage was added at the closest useful level;
- [ ] real GNU Make/OS behavior is exercised when the contract depends on it;
- [ ] public docs were updated if CLI, config, discovery, MCP, security, deployment, or result semantics changed;
- [ ] `make check` passes;
- [ ] `make typecheck` passes for source changes;
- [ ] `make dependency-audit` passes before release;
- [ ] `make package-smoke` passes for packaging/release-sensitive changes.

## Documentation maintenance

Documentation is intentionally Markdown-first: no generated docs framework is required while the project remains small.

`tests/unit/test_docs.py` protects cheap, high-value contracts such as relative links, local anchors, canonical document presence, product naming, CLI command coverage, and schema/presentation references. Do not make tests brittle by asserting ordinary prose word-for-word.

Public classes/functions carry concise docstrings; tricky private logic is documented only where the reason or invariant is non-obvious. Generated API documentation can be added later if there is an actual published API-doc use case.

Release publication is documented separately in [Releasing](releasing.md).
