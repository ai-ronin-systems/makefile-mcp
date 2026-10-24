# Changelog

All notable changes to Makefile MCP are documented here.

## Unreleased

### Added

- `pin` policy: freeze each context's Makefile, tracked includes, and listed scripts at
  startup. Any change makes every later call fail closed until restart, and the refused
  attempts are audited. This closes the gap where an agent that can edit Make code turns an
  exposed target into a shell.
- Audit records are hash-chained (`prev_sha256`), across rotated files, and
  `makefile-mcp doctor` reports an edited, removed, or inserted record.
- `agent_output: full | tail | none`, per task or in `defaults`: how much recipe output MCP
  results return to the model. Output is untrusted text for the model; `tail` and `none`
  shrink the prompt-injection surface and the context spent on logs.
- A CI test replays a hijacked agent's tool calls over a real MCP session, and
  `evals/prompt_injection.py` runs a live Claude agent against poisoned test output and
  reports what it attempted and what the server allowed.
- `docs/threat-model.md`: why agents should not get a shell, threats and controls with the
  tests that prove them, the write-access rule, the policy and audit log, and what the server
  does and does not guarantee.

### Changed

- The approval prompt shows the call as it would run, so a human approves `deploy` with
  `ENV="production"` rather than a bare target name: defaults filled in, values normalized,
  paths resolved. Secret values are masked; other values are JSON-quoted and clipped so
  agent-supplied text cannot reshape the prompt. The CLI asks the same question.

### Fixed

- Over MCP, probes for unknown or unexposed targets and unknown contexts are audited.
  The approval resolver used to fail them before the tool body ran, so nothing was recorded.
- The approval prompt is shown only for calls that would run. A call with invalid or
  undeclared inputs is refused without asking, so the agent cannot put text of its choosing
  in front of the human.
- The CLI and a server writing the same audit log no longer lose records on rotation: each
  record is appended under a file lock instead of through a per-process open file.
- The audit log records every run attempt. Calls refused before validation (unknown or
  unexposed task, undeclared or invalid input) are logged with argument names only, and busy
  or cancelled runs are logged with status `refused` or `cancelled`.

## 0.2.2 — 2026-10-15

### Changed

- Update the MCP Python SDK to 2.1.1 (exact pin), along with pydantic, typer, and dev tooling.

### Fixed

- MCP clients see the reason a call failed: Make diagnostics, invalid inputs, approval refusals,
  and unknown tasks are reported as tool errors with their messages. SDK 2.1 otherwise replaces
  them with a generic "Error executing tool". Unexpected internal errors stay hidden.

### Added

- Releases are listed in the official MCP Registry as `io.github.ai-ronin-systems/makefile-mcp`,
  published by the release workflow with short-lived GitHub OIDC credentials.
- Releases publish only after the full CI matrix passes on the tagged commit; signing and
  publishing jobs run no project code and use no dependency cache.

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
