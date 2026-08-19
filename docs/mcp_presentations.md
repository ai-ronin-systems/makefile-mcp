# MCP presentations

Makefile MCP exposes one authorized application/catalog/executor through three MCP presentation modes:

```text
direct | generic | both
```

Exposure policy and MCP presentation are independent dimensions:

```text
.makefile-mcp.yaml absent/present  -> auto/governed authorization
--tools direct|generic|both     -> client-facing tool inventory
```

Changing presentation never creates another policy or execution path.

## Direct — default

```bash
makefile-mcp serve --tools direct
```

Makefile MCP snapshots the callable catalog at server startup and registers one MCP tool per authorized `(context, target)` pair.

```text
root:test       -> make_test
backend:test    -> make_backend_test
frontend:test   -> make_frontend_test
```

Generated names use MCP-safe characters, are capped at 128 characters, and receive a stable hash suffix only when truncation or collision resolution requires it. The generated name is presentation metadata; authorization and execution retain the original context/target identity.

### Typed governed schemas

Governed variables become direct-tool parameters:

```yaml
tasks:
  deploy:
    variables:
      ENV:
        type: enum
        values: [staging, production]
        required: true
      WORKERS:
        type: integer
        default: 2
      MESSAGE:
        type: string
```

Conceptually:

```text
make_deploy(
    *,
    ENV: Literal["staging", "production"],
    WORKERS: int = 2,
    MESSAGE: str | omitted = omitted,
    preview: bool = false
)
```

Token and path parameters also publish their lexical safe-character patterns in the generated JSON Schema for earlier client feedback. Repository confinement for path values remains an authoritative server-side runtime check.

The generated schema is a client-side convenience, not the authorization boundary. Every invocation still passes through `Application.run_task()`, live catalog authorization, runtime variable validation, context locking, and the common executor.

### Lifecycle

Direct tool **registration** is a server-startup snapshot. If supported Makefile discovery later changes:

- an already registered direct tool re-authorizes against the live catalog when called;
- a newly discovered task does not gain a direct tool until server restart;
- a removed/hidden task may remain visible as a registered name but fails live authorization rather than executing.

This keeps registration simple without making startup state authoritative for execution.

## Generic

```bash
makefile-mcp serve --tools generic
```

Generic mode registers exactly three stable tools:

```text
list_tasks(context: string = "root")

describe_task(
    task: string,
    context: string = "root"
)

run_task(
    task: string,
    variables: object<string,string> = {},
    context: string = "root",
    preview: boolean = false
)
```

`list_tasks` returns the current authorized task definitions plus only those capability mappings whose target is callable in the requested context. `describe_task` returns one live authorized task definition. `run_task` delegates to the same application/executor as direct tools and CLI.

Generic mode is useful when an orchestrator needs a small stable MCP vocabulary or when the callable inventory changes frequently enough that direct startup registration is inconvenient.

## Both

```bash
makefile-mcp serve --tools both
```

Registers both views of the same application state. It does not duplicate execution or authorization logic.

Use `both` only when a client genuinely benefits from target-specific direct schemas **and** generic catalog operations; otherwise prefer one presentation to keep the client tool inventory smaller.

## Success contract

Read-only generic operations and successful task executions return the stable MCP success envelope:

```json
{
  "ok": true,
  "data": {}
}
```

For a successful `run_task` or direct execution, `data` contains the serialized `TaskResult`:

```json
{
  "ok": true,
  "data": {
    "task": "test",
    "context": "root",
    "status": "passed",
    "exit_code": 0,
    "started_at": "...",
    "completed_at": "...",
    "duration_ms": 123,
    "stdout": "...",
    "stderr": "",
    "truncated": false,
    "preview": false
  }
}
```

The executor retains stdout and stderr independently up to the configured per-stream bound.

## Tool-error contract

Makefile MCP does **not** encode execution failures as successful `{ "ok": false }` payloads.

The MCP adapter raises for:

- authorization failures;
- invalid caller inputs;
- busy contexts and other expected request errors;
- Make `failed`, `timeout`, or `error` results.

The MCP SDK therefore marks the call as a tool error (`isError=true`). For non-passing Make execution, the model-visible diagnostic combines retained stdout/stderr, marks executor-side truncation, and is capped at 8 KiB of UTF-8 bytes with a second marker if the MCP diagnostic itself is shortened.

CLI/direct Python embedding callers retain the normalized `TaskResult` model for completed executions; MCP performs this failure mapping only at the adapter boundary.

## Cancellation

MCP cancellation is control flow, not a completed task result. Makefile MCP terminates the normal task process group, completes bounded pipe cleanup, and then re-raises cancellation so the MCP request unwinds normally.

A deliberately detached new session is outside Makefile MCP's documented containment boundary; tasks are expected to be foreground/bounded jobs.

## Progress and completion feedback

Execution tools receive an SDK-injected MCP `Context` that is not exposed in the model-visible input schema. When the client requests progress, Makefile MCP reports truthful lifecycle events:

```text
0 / 1  Starting run: test
1 / 1  Completed run: test
```

or `Starting preview`, `Completed preview`, and `Failed ...` as appropriate.

Makefile MCP does not invent intermediate percentages because GNU Make does not provide generic task-progress information. Progress remains an MCP-adapter concern and never enters `Application`, `TaskExecutor`, or process management.

## Preview

Both presentations expose the same Makefile MCP-owned boolean control:

```text
preview = false   -> normal GNU Make execution
preview = true    -> add GNU Make --dry-run
```

Preview does not bypass authorization, validation, environment filtering, locking, timeout, or output bounds. It is **not a sandbox**: Make evaluation, include remaking, side-effecting functions, or recursive `$(MAKE)` behavior can still have effects.

A successful preview means GNU Make's dry-run invocation completed successfully; it does not guarantee a later real execution will succeed.

## MCP annotations

Catalog/description operations are marked read-only and closed-world. Make execution tools use deliberately conservative annotations: they are not declared read-only or idempotent and are treated as potentially destructive/open-world regardless of Makefile MCP's advisory `risk` metadata.

`risk = unknown|safe|write|dangerous` is repository/client metadata, not a protocol-level safety guarantee.

## Choosing a presentation

| Need | Recommended mode |
| --- | --- |
| ordinary coding agent, small/medium task set | `direct` |
| strongest target-specific schemas/discoverability | `direct` |
| orchestration code with stable tool names | `generic` |
| very large or changing catalogs | `generic` |
| client explicitly needs both interfaces | `both` |

See [Contexts and capabilities](contexts_and_capabilities.md), [CLI reference](cli.md), and [client setup](clients.md).
