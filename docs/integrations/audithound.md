# AuditHound integration pattern

Just Make It MCP (JMIM) contains no AuditHound-specific scanners, evidence models, or audit profiles. It is a generic Make-to-MCP execution boundary.

For orchestration-heavy consumers such as AuditHound, prefer the stable generic MCP presentation:

```bash
make-mcp serve --tools generic
```

It provides:

- `list_tasks`;
- `describe_task`;
- `run_task`;
- context-valid capability mappings;
- governed typed inputs;
- risk and timeout metadata;
- bounded successful task-result output;
- MCP tool errors for authorization, validation, timeout, and non-passing Make execution.

Repository diagnostics remain available separately through `make-mcp doctor` before connecting the orchestrator. The generic MCP presentation intentionally contains only `list_tasks`, `describe_task`, and `run_task`.

For evidence-provider repositories, governed mode is recommended so the orchestration contract is explicit:

```yaml
capabilities:
  appsec_scan: scan-appsec
  sbom: generate-sbom
```

The consuming application should own scanner result parsing, findings/evidence schemas, audit profiles, and workflow semantics. JMIM should not acquire AuditHound-specific adapters unless a generally reusable execution contract emerges from real integrations.

See [Governed mode](../governed_mode.md), [MCP presentations](../mcp_presentations.md), and [Deployment](../deployment.md).
