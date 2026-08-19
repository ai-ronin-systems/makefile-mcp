# Configuration

`.make-mcp.yaml` adds metadata that Make does not conveniently express. It never contains recipes, commands, dependencies, steps, pipelines, executors or runners.

```yaml
schema_version: 1

defaults:
  timeout_seconds: 600
  output_limit_bytes: 1048576

contexts:
  backend:
    directory: backend

tasks:
  deploy:
    enabled: false
    risk: dangerous

  test:
    timeout_seconds: 900
    variables:
      MODULE:
        type: string
      MODE:
        type: enum
        values: [fast, full]

capabilities:
  verify: test

environment:
  inherit: [PATH, HOME, USER]
  allow:
    CI: "1"
```

## Variables

Supported types are `string`, `integer`, `boolean`, `enum` and `path`.

Only declared variables may be supplied. Variable names are validated, enum values require exact membership, control characters are rejected, and path values are confined to the repository after symlink resolution.

The resulting invocation is an argv list such as:

```text
make --no-print-directory test MODULE=security
```

No arbitrary environment or `KEY=VALUE` passthrough exists.

## Contexts

`root` always exists. Configured contexts must resolve to the repository root or one of its descendants. Absolute external paths, `..` escapes and symlink escapes are rejected.

## Capabilities

Capabilities are intentionally just `semantic-name -> target-name` mappings. They do not create a second task model or workflow layer.
