# Governed mode

In Just Make It MCP (JMIM), governed mode turns a repository's Makefile surface into an explicit agent execution contract.

Use it when zero-config exposure is too broad, or when tasks need inputs, contexts, semantic capabilities, risk metadata, or task-specific execution limits.

## Enabling governed mode

Mode selection is intentionally binary and based only on file presence:

```text
.make-mcp.yaml absent  -> auto mode
.make-mcp.yaml present -> governed mode
```

There is no `mode:` setting. Creating `.make-mcp.yaml` immediately changes exposure to deny-by-default. An empty file therefore exposes no tasks.

Configuration is loaded once for an application/server lifetime. If `.make-mcp.yaml` is created, deleted, or edited while JMIM is running, subsequent operations fail closed until the process is restarted. Authorization policy is never hot-reloaded mid-process.

## Minimal governed repository

```yaml
schema_version: 1

tasks:
  test: {}
  lint: {}
```

Only those discovered targets are callable:

```bash
make-mcp list
make-mcp run test
```

A configured name does not create a target. It must also be present in the conservatively discovered Make surface.

## Authorization unit

Authorization is the exact pair:

```text
(context, target)
```

`root:test` and `backend:test` are separate decisions.

```yaml
contexts:
  backend:
    directory: backend
  frontend:
    directory: frontend

tasks:
  test:
    contexts: [backend, frontend]
```

```bash
make-mcp list --context backend
make-mcp run test --context backend
```

Contexts are confined to the repository after symlink resolution. The built-in `root` context always refers to the repository root. See [Contexts and capabilities](contexts_and_capabilities.md) for context discovery, authorization, execution, and monorepo semantics.

## Typed task inputs

Inputs must be declared per task. Supported types are:

```text
token
integer
boolean
enum
path
string
```

Example:

```yaml
tasks:
  deploy:
    risk: dangerous
    variables:
      ENV:
        type: enum
        values: [staging, production]
        required: true
      WORKERS:
        type: integer
        default: 2
      RELEASE_NOTES:
        type: string
```

```bash
make-mcp run deploy ENV=staging WORKERS=4 RELEASE_NOTES='release candidate'
make-mcp run deploy ENV=staging --preview
```

`--preview` asks GNU Make for `--dry-run`; it does not bypass authorization or input validation and is not a side-effect-free sandbox.

The declaration is the contract; undeclared caller variables are rejected. Arbitrary `string` values use a separate JSON data channel rather than GNU Make variable syntax. See [Security](security.md#arbitrary-string-inputs) for the boundary and [Configuration](configuration.md#variables) for the exact schema.

## Capabilities

Capabilities provide stable semantic names for orchestrators without creating a second workflow model:

```yaml
capabilities:
  verify: test
  package: build
  appsec_scan: scan-appsec
```

A capability still resolves through normal context exposure checks. It cannot make a hidden task callable. Capabilities are semantic mappings, not executable aliases; see [Contexts and capabilities](contexts_and_capabilities.md).

## Environment policy

Governed execution receives a filtered child environment. With no explicit environment configuration, JMIM inherits only `PATH`, `HOME`, and `USER` when present. An explicit `environment.inherit` list **replaces** those defaults rather than extending them, while `environment.allow` supplies trusted literal values and wins on duplicate keys.

```yaml
environment:
  inherit: [PATH, HOME, USER, API_TOKEN]
  allow:
    CI: "1"
```

Environment configuration is trusted operator policy, not caller input. See [Configuration](configuration.md#environment) for exact precedence and [Security](security.md#make-variables-and-process-environments) for the trust implications.

## Risk metadata

A governed task may declare:

```text
unknown
safe
write
dangerous
```

Risk is advisory JMIM metadata for clients. It is not authorization, does not imply read-only/idempotent/closed-world MCP behavior, and JMIM does not infer it from target names. Omitted risk is `unknown`. Execution tools therefore use conservative MCP behavioral annotations independently of this field.

## Execution limits

Repository defaults can bound task execution:

```yaml
defaults:
  timeout_seconds: 600
  output_limit_bytes: 1048576
  input_limit_bytes: 1048576
```

A task may override its timeout:

```yaml
tasks:
  integration-test:
    timeout_seconds: 1800
```

See [Configuration](configuration.md) for the complete reference and [Security](security.md) for the resource-boundary rationale.

## Environment policy

Governed mode can explicitly inherit or set environment variables needed by trusted recipes:

```yaml
environment:
  inherit: [PATH, HOME, USER]
  allow:
    CI: "1"
```

This is trusted operator configuration. GNU Make and JMIM control variables are reserved. Do not expose interpreter/process-control names unless that behavior is intentional; see [Security](security.md#make-variables-and-process-environments).

## MCP presentation is independent

Governed mode determines **what is callable**. MCP presentation determines **how callable tasks appear to the client**.

```bash
make-mcp serve --tools direct
make-mcp serve --tools generic
make-mcp serve --tools both
```

See [MCP presentations](mcp_presentations.md).

## Recommended adoption path

Start with auto mode for a trusted developer repository whose discovered Make surface is acceptable. Add `.make-mcp.yaml` when you need one or more of:

- deny-by-default target exposure;
- task parameters;
- monorepo contexts;
- semantic capabilities;
- task risk metadata;
- explicit execution limits or environment policy.

Do not duplicate recipes or workflow logic in `.make-mcp.yaml`. Keep commands, dependencies, ordering, and implementation in Make.

See also [CLI reference](cli.md), [Static Make discovery](discovery.md), and [Security](security.md).
