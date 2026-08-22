# Changelog

All notable changes to Just Make It MCP (JMIM) are documented here.

## Unreleased

## 0.1.0 — 2026-08-22

Initial public release.

### Added

- Zero-configuration discovery of conservatively recognized GNU Make targets.
- Governed deny-by-default exposure through `.make-mcp.yaml`.
- Typed task inputs for tokens, integers, booleans, enums, repository-confined paths,
  and arbitrary strings through a private JSON side channel.
- Explicit repository contexts, capability aliases, risk metadata, and physical-context locking.
- CLI commands for listing, describing, running, previewing, diagnosing, and serving tasks.
- MCP v2 stdio presentation with generic and direct tool modes.
- GNU Make `--dry-run` preview support and MCP start/completion progress feedback.
- Bounded input, stdout/stderr capture, timeouts, cancellation, process-group cleanup,
  stdin isolation, and fail-closed policy-change detection.
- Conservative static Makefile/include discovery without evaluating GNU Make during discovery.
- Linux/macOS CI, package smoke tests, PyPI Trusted Publishing, release provenance,
  and immutable GitHub Actions references.
- Security, architecture, configuration, discovery, CLI, deployment, client, development,
  and release documentation.
