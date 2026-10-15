# Changelog

All notable changes to Makefile MCP are documented here.

## Unreleased

## 0.2.1 — 2026-10-15

Documentation-only release; no code behavior changes.

### Fixed

- README links on PyPI no longer 404: they now point to the GitHub repository.
- README threat model no longer overclaims audit coverage; requests rejected before
  validation are not logged.
- `doctor` auto-mode warning and governed-mode/design docs describe the run-safe auto mode.

## 0.2.0 — 2026-10-15

### Breaking

- Auto mode (no `.makefile-mcp.yaml`) now runs only `test`, `lint`, `check`, and `fmt`. Other
  discovered targets are still listed (with `runnable: false`) but refused at run time and not
  registered as direct MCP tools. Pass `--legacy-auto-run` to restore the old behavior; it prints
  a warning and will be removed in a future release.
- `approval` is a reserved task variable name.

### Added

- Human approval for risky tasks: tasks whose risk is in `defaults.require_approval` (default
  `[dangerous]`) run only after the human confirms through MCP elicitation. Clients that cannot
  elicit are refused. The CLI prompts on a TTY, accepts `--yes`, and refuses otherwise.
- Optional `audit` log: one JSON line per governed call (timestamp, task, context, arguments,
  risk, approval outcome, status, exit code, duration, output size and tail), with size-based
  rotation.
- `secret: true` variable attribute: masked in audit arguments and output tails.

## 0.1.0 — 2026-08-23

Initial public release.

### Added

- Zero-configuration discovery of conservatively recognized GNU Make targets.
- Governed deny-by-default exposure through `.makefile-mcp.yaml`.
- Typed task inputs for tokens, integers, booleans, enums, repository-confined paths,
  and arbitrary strings through a private JSON side channel.
- Explicit repository contexts, capability aliases, risk metadata, and physical-context locking.
- CLI commands for listing, describing, running, previewing, diagnosing, and serving tasks.
- MCP v2 stdio presentation with generic and direct tool modes, collision-safe direct tool names,
  and typed client schema hints.
- GNU Make `--dry-run` preview support and MCP start/completion progress feedback.
- Bounded input, stdout/stderr capture, timeouts, cancellation, process-group cleanup,
  stdin isolation, and fail-closed policy-change detection.
- Conservative static Makefile/include discovery without evaluating GNU Make during discovery.
- Linux/macOS CI, clean-package wheel/sdist and CLI/MCP stdio smoke tests, static type checking,
  runtime dependency vulnerability auditing, PyPI Trusted Publishing, release provenance,
  main-branch tag enforcement, and immutable GitHub Actions references.
- Security, architecture, design-rationale, configuration, discovery, CLI, deployment, client,
  development, and release documentation.
- Self-hosted `.makefile-mcp.yaml` governance for Makefile MCP's own agent-callable maintenance surface.
- MCP Registry `server.json` metadata prepared for publication after the first PyPI release.
- Non-root default Docker runtime user; Compose can still map the host UID/GID for mounted worktrees.
