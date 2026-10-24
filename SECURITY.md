# Security

## Supported version

Makefile MCP is pre-1.0. Security fixes ship in a new patch release of the latest minor version. Older releases are not patched; upgrade to the latest release.

## Security model

Makefile MCP assumes repository Makefiles are trusted operator-controlled code. It constrains the MCP/CLI request boundary; it does not sandbox a trusted Make recipe.

The threat model, written for reviewers deciding whether to connect an agent, is in [docs/threat-model.md](docs/threat-model.md): why agents should not get a shell, threats and controls with the tests that prove them, what the server does and does not guarantee, the policy file, and the audit log.

Implementation details, including auto/governed exposure, human approval for risky tasks, the audit log, GNU Make input handling, arbitrary-string JSON transport, conservative discovery, path/environment controls, execution bounds, and deployment assumptions, are documented in [docs/security.md](docs/security.md).

Governed exposure is documented separately in [docs/governed_mode.md](docs/governed_mode.md).

## Reporting

Use **GitHub Private Vulnerability Reporting** for security reports:

<https://github.com/ai-ronin-systems/makefile-mcp/security/advisories/new>

Do not open a public issue for an undisclosed vulnerability.

Include:

- affected version;
- reproduction conditions;
- expected and actual behavior;
- security impact;
- proposed mitigation when available.

Avoid publishing a working exploit before maintainers have had a reasonable opportunity to investigate and ship a fix.
