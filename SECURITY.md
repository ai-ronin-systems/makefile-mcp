# Security

## Supported version

Before the first public release, security fixes target `main`. After publication, fixes target the latest published pre-1.0 release and the current development line as appropriate.

## Security model

Makefile MCP assumes repository Makefiles are trusted operator-controlled code. It constrains the MCP/CLI request boundary; it does not sandbox a trusted Make recipe.

The complete threat model, including auto/governed exposure, GNU Make input handling, arbitrary-string JSON transport, conservative discovery, path/environment controls, execution bounds, and deployment assumptions, is documented in [docs/security.md](docs/security.md).

Governed exposure is documented separately in [docs/governed_mode.md](docs/governed_mode.md).

## Reporting

Use **GitHub Private Vulnerability Reporting** for security reports:

<https://github.com/ai-ronin-systems/makefile-mcp/security/advisories/new>

Repository owners must enable Private Vulnerability Reporting before the first public release. Do not open a public issue for an undisclosed vulnerability.

Include:

- affected version;
- reproduction conditions;
- expected and actual behavior;
- security impact;
- proposed mitigation when available.

Avoid publishing a working exploit before maintainers have had a reasonable opportunity to investigate and ship a fix.
