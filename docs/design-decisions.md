# Design decisions

These decisions are stable enough to document, but not large enough to justify an ADR hierarchy in V1.

1. **Make is authoritative.** Recipes, dependencies, ordering and workflow stay in Make.
2. **Discovery is not authorization.** Only configured, documented, or `.PHONY` targets become public.
3. **Configuration is metadata-only.** There is no command, shell, pipeline, runner or dependency DSL.
4. **Execution never uses a shell.** Validated arguments are passed directly to `make` as argv.
5. **MCP V1 uses stdio and exposes three tools.** `list_tasks`, `describe_task`, `run_task`.
6. **One task per context.** File locking coordinates independent CLI/MCP processes without a scheduler.
7. **Capabilities stay mappings.** Semantic capability names map directly to Make targets.
8. **No plugin/result-parser framework in V1.** Raw stdout/stderr plus stable task status are sufficient until real usage proves otherwise.
