# Configuration reference

In Makefile MCP, `.makefile-mcp.yaml` is optional. Its **presence** enables governed mode; its contents define the governed execution contract.

For the operating model and adoption guidance, read [Governed mode](governed_mode.md). This document is the field-level reference.

## Complete example

```yaml
schema_version: 1

defaults:
  timeout_seconds: 600
  output_limit_bytes: 1048576
  input_limit_bytes: 1048576
  require_approval: [dangerous]

contexts:
  backend:
    directory: backend

tasks:
  test:
    contexts: [root, backend]
    risk: safe
    timeout_seconds: 900
    description: Run the test suite
    variables:
      MODULE:
        type: token
      MODE:
        type: enum
        values: [fast, full]
      WORKERS:
        type: integer
      CI:
        type: boolean
      REPORT:
        type: path
      MESSAGE:
        type: string
      API_TOKEN:
        type: string
        secret: true

  deploy:
    enabled: false
    contexts: [root]
    risk: dangerous

capabilities:
  verify: test

environment:
  inherit: [PATH, HOME, USER]
  allow:
    CI: "1"

audit:
  path: .makefile-mcp/audit.jsonl
  max_bytes: 10485760
  backup_count: 3
```

Unknown fields are rejected.

## `schema_version`

```yaml
schema_version: 1
```

Current schema version: `1`.

## `defaults`

```yaml
defaults:
  timeout_seconds: 600
  output_limit_bytes: 1048576
  input_limit_bytes: 1048576
```

- `timeout_seconds`: default task timeout; positive integer.
- `output_limit_bytes`: retained bound **per stream**, applied independently to stdout and stderr; minimum 4 KiB, maximum 16 MiB per stream.
- `input_limit_bytes`: maximum encoded caller-input mapping and arbitrary-string JSON payload; 1 byte to 16 MiB.
- `require_approval`: risk levels that need explicit human approval before running (or previewing); default `[dangerous]`, `[]` disables. Over MCP the server asks through elicitation and refuses when the client cannot ask; the CLI prompts on a TTY, accepts `--yes`, and refuses otherwise.
- `agent_output`: how much recipe output MCP results return to the model: `full` (default), `tail` (the last 2000 characters of each stream), or `none` (status and exit code only). Applies to passing and failing runs. The CLI and the audit log are not affected. Recipe output is untrusted text for the model, so narrow it where the agent does not need it.

## `contexts`

```yaml
contexts:
  backend:
    directory: backend
```

`root` is built in and reserved. Additional context names must match:

```text
[A-Za-z0-9][A-Za-z0-9_.-]*
```

Context directories must resolve to the repository root or a descendant after symlink resolution. For operational semantics, see [Contexts and capabilities](contexts_and_capabilities.md).

## `tasks`

```yaml
tasks:
  test:
    enabled: true
    contexts: [root]
    description: Run tests
    risk: safe
    timeout_seconds: 900
    variables: {}
```

Fields:

- `enabled`: boolean, default `true`.
- `contexts`: authorized contexts, default `[root]`; cannot be empty.
- `description`: optional client-facing description; overrides discovered `##` text.
- `risk`: optional `unknown | safe | write | dangerous`; omitted becomes `unknown`.
- `timeout_seconds`: optional positive per-task timeout override.
- `variables`: declared caller input contract.
- `agent_output`: optional `full | tail | none` override of `defaults.agent_output`.

A task entry never creates a Make target. The target must also be conservatively discovered in that context.

## Resolution and precedence

| Contract | Resolution rule |
| --- | --- |
| task timeout | `tasks.<name>.timeout_seconds` -> `defaults.timeout_seconds` |
| task description | configured `description` -> discovered `##` description -> none |
| task risk | configured `risk` -> `unknown` |
| task agent output | `tasks.<name>.agent_output` -> `defaults.agent_output` -> `full` |
| task contexts | configured `contexts` -> `[root]` |
| environment inheritance | configured `environment.inherit` -> default `[PATH, HOME, USER]`; configured list replaces the default |
| explicit environment values | `environment.allow` is applied after inherited values and therefore wins on duplicate keys |

Configuration never creates a task: the final callable contract is always **configured exposure intersected with conservative discovery**.

## Variables

```yaml
variables:
  NAME:
    type: token
    required: false
    description: Optional description
    default: value
```

Variable fields:

| Field | Default | Meaning |
| --- | --- | --- |
| `type` | `token` | transport/validation type |
| `required` | `false` | caller must provide a value when no default exists |
| `description` | none | client/schema help text |
| `values` | `[]` | non-empty allowlist required only for `enum` |
| `default` | none | fallback value validated under the declared type |
| `secret` | `false` | mask the value in the audit log (arguments and output tail); cannot have a `default` |

`required: true` and `default` are mutually exclusive and rejected. `secret` only affects auditing: the value still reaches Make as its type dictates, so prefer `type: string` for secrets to keep them off the `make` command line.

Variable names must be ordinary identifiers, must not be Python keywords such as `class` or `async`, and cannot use reserved GNU Make and Makefile MCP control names. `preview` and `approval` are also reserved because it is the cross-presentation Makefile MCP execution-preview control. The Python-keyword restriction keeps one governed contract valid in both generic and direct MCP presentations. A variable cannot be both `required: true` and have a `default`; those contracts are contradictory and are rejected at configuration load.

### `token`

A compact Make-safe scalar. Allowed value grammar:

```text
letters digits . _ / @ : + -
```

The first character must be alphanumeric.

### `integer`

Parsed as base-10 integer and normalized before execution.

### `boolean`

Accepted true forms:

```text
1 true yes on
```

Accepted false forms:

```text
0 false no off
```

Values are normalized before execution.

### `enum`

```yaml
MODE:
  type: enum
  values: [fast, full]
  default: fast
```

`values` is required and non-empty. Enum values must also satisfy the safe scalar grammar.

### `path`

Uses the safe path grammar and must resolve within the repository after symlink resolution.

`path` values are transported to GNU Make as normalized absolute `NAME=value` assignments.
Consequently, the **resolved absolute path** must also fit the safe path grammar. Currently, a
repository whose own absolute pathname contains whitespace cannot use a governed `path` input;
use a wrapper target with a safe repository path or a `string` input consumed from
`MAKEFILE_MCP_INPUT` when arbitrary path-like text is required.

### `string`

Accepts arbitrary text, including whitespace and newlines. String values do not use direct GNU Make variable transport; they are serialized into the private per-invocation JSON payload referenced by `MAKEFILE_MCP_INPUT`.

See [Security: arbitrary string inputs](security.md#arbitrary-string-inputs) for the transport boundary and recipe contract.

## `capabilities`

```yaml
capabilities:
  verify: test
  package: build
```

Capabilities are semantic-name to target-name mappings. Resolution remains context-scoped and subject to normal exposure checks. They do not create executable aliases or bypass `(context, target)` authorization. See [Contexts and capabilities](contexts_and_capabilities.md).

## `environment`

```yaml
environment:
  inherit: [PATH, HOME, USER]
  allow:
    CI: "1"
```

Makefile MCP constructs a **fresh filtered child environment** for GNU Make; it does not inherit the full parent process environment.

| Configuration | Effective behavior |
| --- | --- |
| no `environment:` section | inherit `PATH`, `HOME`, and `USER` when present |
| explicit `inherit:` | **replaces** the default list; it does not append to it |
| `allow:` | inject trusted literal string values |
| same key in `inherit` and `allow` | `allow` wins |
| parent variable not named in `inherit` | not passed to GNU Make |

For example, to add `API_TOKEN` while preserving the normal execution environment:

```yaml
environment:
  inherit:
    - PATH
    - HOME
    - USER
    - API_TOKEN
```

Using only `inherit: [API_TOKEN]` intentionally removes `PATH`, `HOME`, and `USER` from the inherited set. If no effective `PATH` is supplied, process execution falls back to the platform default executable-search path. `makefile-mcp doctor` checks GNU Make availability against this same effective `PATH`.

GNU Make and Makefile MCP control variables are rejected. Environment configuration is trusted operator policy; see [Security](security.md#make-variables-and-process-environments).

## `audit`

```yaml
audit:
  path: .makefile-mcp/audit.jsonl   # relative to the repository root
  max_bytes: 10485760               # rotate after this size
  backup_count: 3                   # rotated files kept; 0 never rotates
```

Optional. Appends one JSON line per run attempt, whatever its outcome:

| Field | Meaning |
| --- | --- |
| `timestamp`, `task`, `context` | what was asked and when |
| `arguments` | declared inputs, `secret: true` values masked |
| `risk` | the task's risk, or `null` if the task was never resolved |
| `approval` | `not_required`, `approved`, `denied`, `unavailable`, or `not_evaluated` |
| `status` | `passed`, `failed`, `error`, `timeout`, `refused`, or `cancelled` |
| `reason` | why a call was refused, when it was |
| `preview`, `exit_code`, `duration_ms` | how it ran |
| `output_bytes`, `output_tail` | output size and the last 2000 characters, secrets masked |
| `prev_sha256` | SHA-256 of the previous line, or `null` for the first record |

Calls refused before their inputs are validated (unknown or unexposed task, undeclared or invalid input) are recorded with `approval: not_evaluated` and argument **names only**: secrecy is not known yet, so no value is written. A call refused because its context is busy, and a run cancelled by the client, are recorded too. Calls the MCP SDK rejects before Makefile MCP runs (an unknown tool, a direct tool argument that fails its schema) are not.

Records form a hash chain across rotated files. `makefile-mcp doctor` verifies it and reports `audit.chain_broken` when a record was edited, removed, or inserted. The CLI and a server can write the same log safely: each record is chained and appended under a file lock.

The chain makes tampering evident, not impossible. Recipes run as the same user, so they could rewrite the whole log and recompute every hash. Ship records, or at least the latest `prev_sha256`, off the host if the log must hold up. See [Threat model](threat-model.md#audit-log).

## `pin`

```yaml
pin:
  make_sources: true        # default when `pin` is present
  paths: [scripts, config]  # extra files or directories recipes run
```

Optional. Freezes trusted files at startup, the same way `.makefile-mcp.yaml` is frozen. If a pinned file changes, appears, or disappears, every later call fails closed with a restart-required error, and run attempts are audited as refused.

- `make_sources` pins each context's `Makefile` and its literal includes, including those inside conditional blocks. Files included from a conditionally included file are not tracked; list them in `paths`.
- `paths` are repository-relative files or directories. Directories are walked, and their listings are pinned too, so added or renamed files count as changes. Symlinked directories are followed when they stay in the repository. A path, or a symlink, that leaves the repository is a startup error.

Pinning is for agents that run trusted automation but must not change it. It detects changes through file metadata (size, timestamps including `ctime`, inode, symlink target), which a process running as the same user cannot reset. It does not cover files reached through dynamic includes (`include $(VAR)`), tools on `PATH`, or anything outside the pinned paths. Pinning is checked before each call starts, so a change made while a task runs is caught by the next call, not the running one. See [Threat model](threat-model.md#the-write-access-rule).

## Exposure and presentation are not configuration keys

Exposure mode is selected only by `.makefile-mcp.yaml` presence:

```text
absent  -> auto
present -> governed
```

MCP presentation is selected at server startup, not in YAML:

```bash
makefile-mcp serve --tools direct
makefile-mcp serve --tools generic
makefile-mcp serve --tools both
```

See [MCP presentations](mcp_presentations.md).

## Reload semantics

Configuration presence and contents are loaded once per application/server lifetime. If `.makefile-mcp.yaml` is added, removed, or changed while Makefile MCP is running, subsequent operations fail closed and require restart; policy is never hot-reloaded mid-process.

Makefile discovery has a separate cache and refreshes when the conventional Makefile or tracked literal includes change. See [Architecture](architecture.md#lifecycle-and-caching).

See also [CLI reference](cli.md) and [Static Make discovery](discovery.md).
