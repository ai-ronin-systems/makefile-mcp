# Security model

Make MCP protects the CLI/MCP request boundary from becoming an arbitrary command, environment injection, or path traversal surface. It does not sandbox repository Makefiles: the operator is assumed to trust the repository code they choose to expose.

## Guardrails

- discovery does not equal authorization;
- no arbitrary shell/command MCP tool;
- config is metadata-only;
- only declared variables are accepted;
- context and path variables remain inside the repository after real-path resolution;
- execution uses `asyncio.create_subprocess_exec`, never a shell;
- child stdout/stderr are separated, fully drained and retained only up to configured byte limits;
- timeout and cancellation terminate the dedicated process group, escalating to SIGKILL if needed;
- one active task per context is enforced with a cross-process file lock;
- callers cannot inject arbitrary environment variables;
- full environment values are not logged;
- MCP stdio is reserved for the protocol.

## Risk metadata

`safe`, `write` and `dangerous` are client-facing metadata. Risk classification never replaces exposure checks. `doctor` warns when dangerous tasks are public.

## Threat boundary

A malicious or compromised Makefile can execute arbitrary repository-authorized code when its exposed target is run. Make MCP is not a sandbox, container runtime, authentication layer, or policy engine for untrusted repositories.
