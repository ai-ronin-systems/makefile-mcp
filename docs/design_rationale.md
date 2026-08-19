# Design rationale

Makefile MCP deliberately keeps a narrow job: expose existing, trusted GNU Make automation to MCP clients without creating a second workflow system or a generic command runner.

The repository, Makefiles, included Make code, wrapper scripts, and provisioned tools are trusted operator-controlled code. The request boundary is narrower: an MCP/CLI caller chooses an exposed operation and, in governed mode, supplies declared input values. Makefile MCP constrains that request boundary; it does not attempt to sandbox hostile Make code.

## Core design choices

| Decision | Alternative deliberately not taken | Why |
| --- | --- | --- |
| Keep GNU Make as the source of truth | Define commands again in YAML or another workflow DSL | Avoids two execution models and configuration drift. |
| Discover targets conservatively without evaluating Make | Use GNU Make itself as a discovery oracle or implement a complete parser | Discovery should not execute trusted build logic merely to construct the tool catalog; ambiguous syntax is better omitted than guessed. |
| Expose governed tasks/capabilities rather than a generic shell | Provide an arbitrary command-execution MCP tool | Keeps the agent-facing capability surface aligned with repository-owned automation. |
| Treat caller values separately from trusted Make code | Assume `shell=False` makes every Make assignment safe | GNU Make is itself an interpreter; declared inputs therefore use constrained scalar transport or a JSON data channel for arbitrary strings. |
| Keep one catalog/validator/executor path | Implement separate CLI, generic-MCP, and direct-MCP execution paths | Prevents authorization, validation, preview, timeout, and result semantics from drifting between interfaces. |
| Use stdio only | Add HTTP, authentication, TLS, tenancy, and service lifecycle | Remote-service concerns are a different product boundary and are unnecessary for local MCP process launch. |
| Bound foreground execution | Become a scheduler, daemon supervisor, or workflow engine | Makefile MCP is an adapter around Make tasks, not an orchestration platform. |

## Product properties

### Request boundary and governance

- No arbitrary shell/command MCP tool: callers invoke discovered or explicitly governed Make targets.
- Auto mode is zero-configuration for trusted local repositories and disables caller-controlled Make variables.
- Governed mode is deny-by-default over `(context, target)` pairs and accepts only declared inputs.
- GNU Make and Makefile MCP control names such as `SHELL`, `MAKEFLAGS`, `MAKEFILES`, `MAKEOVERRIDES`, `VPATH`, and `MAKEFILE_MCP_INPUT` cannot be caller task inputs.
- `token`, `enum`, `integer`, `boolean`, and `path` inputs are validated and normalized before Make assignment transport.
- Arbitrary `string` inputs use a private per-invocation JSON data channel rather than `NAME=<arbitrary text>` Make syntax.
- Context directories and governed `path` inputs stay within the repository after symlink resolution.
- Discovery inspects the conventional context `Makefile`, and execution pins that same top-level file with `make -f`.
- Conservative discovery omits syntax it cannot classify safely rather than expanding the callable surface speculatively.

### Runtime correctness

These are primarily execution-reliability properties, not claims that Makefile MCP sandboxes trusted Make code:

- input size and retained stdout/stderr are bounded;
- recipe stdin is `/dev/null`, so MCP stdio cannot leak into child processes;
- timeout and cancellation terminate the task process group and clean up same-group descendants;
- final pipe draining is bounded so inherited descriptors cannot hang result collection indefinitely;
- one active task per resolved physical context is enforced across processes, including aliases of the same directory;
- preview uses GNU Make `--dry-run` through the same authorization, validation, locking, timeout, and output path;
- subprocess-start, timeout, cancellation, Make failure, and truncation are normalized into stable results/errors.

### MCP presentation

- Direct mode registers one typed MCP tool per callable `(context, target)` pair.
- Generic mode exposes `list_tasks`, `describe_task`, and `run_task` for stable orchestrator integration and large catalogs.
- Both modes share the same catalog, authorization, validator, executor, and result semantics.
- Direct-tool names are normalized, bounded, and collision-safe.
- Direct-tool schemas expose governed input types to clients, while executor-side validation remains authoritative.
- Authorization, validation, timeout, and Make failures surface as MCP tool errors.
- Progress reporting emits truthful started/completed/failed events rather than synthetic percentages.

### Repository evolution

- Supported Makefile/include changes refresh the discovered catalog at runtime.
- `.makefile-mcp.yaml` is startup-stable authorization policy; changing it fails closed until restart.
- Direct MCP tool inventory is a startup snapshot because tool registration is protocol-facing state.
- Existing direct-tool invocations still re-enter the live catalog before execution.
- Contexts provide monorepo working-directory and authorization scoping.
- Capabilities provide semantic names such as `verify` or `package` that map to already-authorized Make targets without creating executable aliases or orchestration logic.

### Distribution and operation

- Linux and macOS are supported; Windows is intentionally out of scope for `0.1.0`.
- `doctor` checks runtime, discovery, configuration, context aliasing, and operating assumptions.
- The Python package supports `pipx`, `uv tool`, and one-shot `uvx` use.
- CI covers Python 3.11–3.14 on Linux/macOS, branch coverage, formatting/linting, package installation smoke tests, Docker build, MCP stdio smoke, static typing, and runtime dependency vulnerability auditing.
- Releases use a version/tag/changelog identity check, clean wheel/sdist validation, PyPI Trusted Publishing, provenance attestation, and GitHub Releases.

## Scope discipline

Makefile MCP intentionally does not provide an HTTP listener, remote authentication, TLS, scheduler, queue, persistent workflow state, plugin execution framework, arbitrary shell capability, or Makefile sandbox. Those features would enlarge the trust and operational model without improving the core job of exposing repository-owned Make automation to local MCP clients.

See [Security](security.md) for the precise trust model, [Architecture](architecture.md) for module/runtime boundaries, and [Governed mode](governed_mode.md) for the operator-facing policy model.
