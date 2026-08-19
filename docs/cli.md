# CLI reference

`make-mcp` is the stable command-line entry point for Just Make It MCP (JMIM). The CLI is a thin adapter over the same `Application`, catalog, authorization, validation, and executor used by MCP.

## Global options

```text
make-mcp [--root PATH] [--version] COMMAND ...
```

| Option | Meaning |
| --- | --- |
| `--root PATH` | Start repository-root detection from `PATH`; defaults to the current directory. |
| `--version` | Print the JMIM package version and exit. |

`--root` is a **root-detection starting path**, not a forced Makefile directory. JMIM searches upward for the nearest `.make-mcp.yaml` or `.git` boundary; only when neither exists does it fall back to the nearest conventional `Makefile`. This prevents a distant parent policy from binding a nearer repository boundary.

## `list`

```text
make-mcp list [--context NAME] [--json]
```

Lists callable tasks for one context. The default context is `root`.

Human output shows the target name and advisory risk. `--json` emits the serialized task definitions used by the application contract.

## `describe`

```text
make-mcp describe TASK [--context NAME] [--json]
```

Describes one callable task after discovery and exposure policy have been applied. The result includes context, risk, timeout, description, and governed variable contracts.

## `run`

```text
make-mcp run TASK [KEY=VALUE ...] [--context NAME] [--preview] [--json]
```

Runs one callable target through the common execution path.

- caller variables use `KEY=VALUE` syntax and must be declared in governed mode;
- duplicate variables are rejected;
- `--preview` adds GNU Make `--dry-run` to the authorized invocation; it is **not** a sandbox;
- `--json` emits the normalized `TaskResult`.

### Task result contract

| Field | Meaning |
| --- | --- |
| `task` | Original GNU Make target name. |
| `context` | Execution context name. |
| `status` | `passed`, `failed`, `timeout`, or `error`. |
| `exit_code` | Process exit code when available. |
| `started_at` / `completed_at` | UTC execution timestamps. |
| `duration_ms` | Measured process lifecycle duration. |
| `stdout` / `stderr` | Retained bounded process output. |
| `truncated` | At least one retained stream exceeded its configured bound. |
| `preview` | Invocation used GNU Make `--dry-run`. |

`preview=true` with `status=passed` means the GNU Make dry-run invocation completed successfully. It does **not** guarantee that a later real execution will succeed or be side-effect free.

## `doctor`

```text
make-mcp doctor [--json]
```

Runs read-only diagnostics over runtime availability, contexts, conservative discovery, configured exposure, capabilities, and operating assumptions. It does not execute task recipes.

A clean result exits `0`; a diagnostic result containing an error exits `1`.

## `serve`

```text
make-mcp serve [--tools direct|generic|both]
```

Runs the stdio MCP server. `direct` is the default. No HTTP listener, TLS layer, or network authentication service is created by JMIM.

See [MCP presentations](mcp_presentations.md) and [client setup](clients.md).

## Exit codes

| Exit | Contract |
| ---: | --- |
| `0` | CLI operation succeeded; for `run`, the task status is `passed`. |
| `1` | Operation completed but reported an unsuccessful result, such as a failed/timed-out task or failing `doctor`. |
| `2` | Invalid CLI usage or an expected JMIM domain/configuration error prevented the operation. |

For automation, prefer `--json` when structured output is required, but continue to use the process exit code as the top-level success/failure signal.

## Repository-root examples

From a repository subdirectory:

```bash
make-mcp list
```

JMIM searches upward for the nearest repository/config boundary.

For clients whose working directory is unpredictable, provide a stable starting path:

```bash
make-mcp --root /absolute/path/to/repo serve --tools direct
```

The path should identify the intended repository tree; it does not bypass root-detection rules.
