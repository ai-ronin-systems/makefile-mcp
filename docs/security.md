# Security model

Makefile MCP is a constrained execution boundary around **trusted repository automation**. It is not a sandbox for untrusted Makefiles.

The repository and its Makefiles are trusted operator-controlled code. If `.makefile-mcp.yaml` exists, that configuration is trusted too. The untrusted side of the boundary is the MCP/CLI caller choosing callable operations and supplying declared inputs.

## Trust boundary

| Component/input | Trust assumption |
| --- | --- |
| repository `Makefile` and reachable included Make code | trusted executable code |
| repository wrapper scripts and provisioned recipe tools | trusted executable/runtime code |
| `.makefile-mcp.yaml` | trusted operator policy |
| MCP/CLI task/context selection | untrusted request input; must be authorized |
| caller task-variable values | untrusted request data; validated/bounded |
| host/container permissions and injected secrets | deployment responsibility outside Makefile MCP |
| any network wrapper around stdio Makefile MCP | separate service boundary outside Makefile MCP |

Makefile MCP constrains what an untrusted caller can ask trusted repository automation to do. It does not make hostile repository code safe.

Timeouts, bounded output, process-group cleanup, stdin isolation, and locking are important runtime-correctness controls. They reduce failure and resource-leak modes around trusted automation, but they are not presented as a sandbox or as protection from malicious Make recipes.

## Exposure policy

Makefile MCP has two exposure policies:

- **auto mode** — no `.makefile-mcp.yaml`; every conservatively discovered root target is callable and caller variables are disabled;
- **governed mode** — `.makefile-mcp.yaml` exists; only explicitly enabled `(context, target)` pairs are callable and only declared inputs are accepted.

Governed-mode behavior and setup are documented in [Governed mode](governed_mode.md). This document focuses on security properties rather than the configuration workflow.

## GNU Make is an interpreter boundary

Avoiding `shell=True` is necessary but insufficient. GNU Make itself expands variables and provides functions such as `$(shell ...)`.

Makefile MCP therefore does not attempt to quote arbitrary caller text safely through GNU Make. Inputs use two deliberately different transports.

### Constrained scalar inputs

`token`, `enum`, `integer`, `boolean`, and `path` are validated and normalized before becoming `NAME=value` arguments to GNU Make.

Textual direct values use a narrow character grammar; `path` values additionally resolve inside the repository after symlink resolution. Because the normalized absolute path itself crosses GNU Make as `NAME=value`, repositories whose absolute pathname contains whitespace cannot use governed `path` inputs in `0.1.0`. GNU Make and Makefile MCP control variable names are reserved.

These types constrain the **transport boundary**, not arbitrary recipe semantics: `token` means Make-lexically safe, `enum` adds an operator allowlist, and `path` adds repository confinement. A trusted recipe can still misuse a syntactically safe value, so choose the narrowest type appropriate to the recipe.

### Arbitrary string inputs

`type: string` accepts arbitrary text, but the value never becomes a normal Make variable assignment.

For a task declaring string inputs, Makefile MCP creates a private per-invocation JSON payload:

```text
caller string
    |
    v
/tmp/makefile-mcp-*/input.json
    |
    | generated pathname only
    v
MAKEFILE_MCP_INPUT=/tmp/.../input.json
    |
    v
make -f /repo/Makefile target
```

The temporary directory is private, `input.json` is mode `0600`, and cleanup occurs after success, failure, timeout, or cancellation. `defaults.input_limit_bytes` bounds the complete encoded caller-input mapping before type conversion and also bounds the encoded string JSON payload, preventing oversized argv/path inputs as well as unbounded temporary writes.

A trusted recipe passes the path to code that parses JSON as data:

```make
publish:
	python3 scripts/publish.py "$(MAKEFILE_MCP_INPUT)"
```

```python
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    message = json.load(handle)["MESSAGE"]
```

Code consuming the JSON must continue treating values as data. Do not `eval` them, generate shell source from them, or feed them back into another interpreter without that interpreter's own safe data boundary.

## Exact Makefile execution

Discovery inspects the conventional `<context>/Makefile`. GNU Make may otherwise prefer `GNUmakefile` or lowercase `makefile`, so execution always pins the exact inspected file:

```text
make --no-print-directory -f <context>/Makefile <target> ...
```

This pins execution to the same **top-level** Makefile used for discovery. GNU Make remains authoritative for dynamic/generated includes and final effective recipe resolution. All Make code reachable by that trusted execution graph—including dynamic or external includes—is therefore part of the trusted execution boundary. Makefile MCP does not sandbox GNU Make filesystem reads.

## Conservative static discovery

Makefile MCP discovers callable names without evaluating GNU Make. It intentionally models only syntax that can be classified conservatively, preferring false negatives over accidental target exposure. It does **not** use GNU Make itself as a discovery oracle.

The authoritative supported/ignored/fail-closed syntax contract, include behavior, cache invalidation, and rationale are documented in [Static Make discovery](discovery.md).

## Paths and contexts

Repository and context boundaries are resolved through the filesystem, not string-prefix checks. Context directories and `path` inputs must remain inside the repository after symlink resolution.

Root detection prefers the nearest `.makefile-mcp.yaml` or `.git` boundary before falling back to a standalone Makefile, preventing a more distant parent policy from binding a nested repository.

## Make variables and process environments

Makefile MCP builds a fresh filtered child environment. By default it inherits only `PATH`, `HOME`, and `USER` when present. Configuring `environment.inherit` **replaces** that default list; it does not append to it. `environment.allow` is applied after inheritance and therefore wins when the same key appears in both. Parent environment variables not explicitly inherited are not passed to GNU Make.

This is a security property as well as an operational constraint. If a recipe needs an additional parent variable, add it deliberately while retaining the normal defaults when required:

```yaml
environment:
  inherit: [PATH, HOME, USER, API_TOKEN]
```

GNU Make may export command-line variable assignments to recipe processes. A declared scalar input can therefore be visible both as a Make variable and as an environment variable inside a recipe. Scalar `token`, `integer`, `boolean`, `enum`, and `path` values also cross GNU Make as command-line assignments and may be visible to same-host process inspection; do not use them as a secret-storage channel.

Variable names are part of trusted governed configuration. Do not expose process/interpreter-control names such as `PATH`, `PYTHONPATH`, `BASH_ENV`, loader variables, or tool-specific control variables unless that behavior is intentional.

Makefile MCP explicitly reserves GNU Make and Makefile MCP control names such as `SHELL`, `MAKEFLAGS`, `MAKEFILES`, `MAKEOVERRIDES`, `VPATH`, and `MAKEFILE_MCP_INPUT`. Those names cannot be caller task inputs or configured environment controls.

## Process and resource bounds

Execution uses argv-based subprocess creation; Python does not invoke a shell to construct the Make command.

The runtime also applies:

- non-interactive task stdin (`/dev/null`), so recipes cannot consume the MCP stdio protocol stream;
- task timeouts;
- bounded stdout/stderr retention, with the configured output limit applied independently to each stream;
- bounded MCP **error** diagnostics (8 KiB of UTF-8-encoded combined stdout/stderr text); diagnostics explicitly mark executor-side truncation and any additional MCP-side truncation, while successful MCP task results retain the configured per-stream bounds and can therefore be substantially larger;
- bounded final pipe draining;
- process-group termination with escalation on timeout/cancellation;
- cleanup of same-process-group background descendants after normal Make completion;
- one active task per resolved physical context directory through a cross-process POSIX lock;
- bounded complete caller input and arbitrary-string payloads.

Normal execution may continue draining output after the retention cap; the retained result remains bounded. Final draining is itself bounded so a detached descendant holding inherited descriptors cannot keep a request open indefinitely. Makefile MCP tasks are foreground/bounded jobs, not daemon launchers; a process that deliberately detaches into a new session leaves Makefile MCP's process-group containment boundary and is unsupported.

## MCP presentation does not change policy

`direct`, `generic`, and `both` are presentation choices only. Every invocation reaches the same `Application`, live catalog authorization, input validation, context lock, and executor.

Direct tool schemas improve client-side validation but are not trusted as the sole security boundary; executor validation still applies.

At the MCP adapter boundary, authorization/validation failures and non-passing Make executions are surfaced as MCP **tool errors** rather than successful structured payloads. Client cancellation is a control-flow signal: Makefile MCP cleans the normal task process group and then propagates cancellation instead of converting it into a successful `TaskResult`. CLI and direct Python embedding callers still use the normalized task-result model for completed executions.

See [MCP presentations](mcp_presentations.md).

## Configuration and reload boundary

`.makefile-mcp.yaml` presence and contents are startup policy and are not hot-reloaded. Makefile MCP fingerprints that policy state at startup; if the file appears, disappears, or changes, subsequent catalog/execution operations fail closed with a restart-required error.

Direct tool registration is also a startup snapshot, while each direct invocation re-enters the live catalog before execution. Supported Makefile discovery changes refresh at runtime; authorization-policy changes require restart.

## Stdio and deployment boundary

The built-in MCP server uses stdio and does not open a network listener or implement a network authentication layer. Authentication, isolation, filesystem permissions, container privileges, secret injection, and host exposure are deployment responsibilities around the process.

For container guidance, including custom tool provisioning, see [Deployment](deployment.md).

## Threat boundary summary

Makefile MCP protects the request boundary from becoming an accidental general Make/shell input language. It does **not** protect against:

- malicious trusted Makefiles;
- a callable target intentionally executing destructive commands;
- unsafe code inside a recipe consuming otherwise safe data;
- an operator intentionally exposing dangerous task names, environment variables, paths, or capabilities;
- host/container privileges granted outside Makefile MCP.

Security reporting instructions are in the repository [SECURITY.md](../SECURITY.md).

## Preview is not a sandbox

`makefile-mcp run ... --preview` and MCP `preview=true` use GNU Make `--dry-run` on the same authorized invocation. This is useful for inspecting the recipes Make intends to run, but it is not a security boundary and does not weaken any existing authorization, validation, locking, timeout, or output controls. GNU Make evaluation can still have side effects, including side-effecting Make functions, remaking included Makefiles, and recursive `$(MAKE)` behavior. Do not use preview as proof that a target is safe to execute.
