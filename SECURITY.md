# Security

## Supported version

Security fixes target the latest `0.1.x` release while the project is pre-1.0.

## Boundary

Make MCP assumes the repository and its Makefiles are code trusted by the operator. It protects the CLI/MCP request boundary from becoming an arbitrary command, environment-injection or path-traversal surface; it does not sandbox a trusted Make recipe.

Do not expose a dangerous target unless that exposure is intentional. `risk` metadata is advisory and never replaces server-side exposure checks.

See `docs/security.md` for the detailed threat boundary and guardrails.

## Reporting

Report vulnerabilities privately to the project maintainers with the affected version, reproduction conditions, impact and proposed mitigation when available. Avoid publishing a working exploit before maintainers have had a reasonable opportunity to address it.
