# MCP client setup

Makefile MCP is a standard local stdio MCP server. Client integrations launch the existing `makefile-mcp` CLI; Makefile MCP does not contain Codex-, Claude-, LangChain-, Cursor-, or VS Code-specific execution code.

The examples below pass an explicit repository root so client working-directory behavior cannot silently select the wrong project:

```text
makefile-mcp --root /absolute/path/to/repo serve --tools direct
```

Use an absolute path and replace `/absolute/path/to/repo` in every example.

> **Stability boundary:** the `makefile-mcp ... serve` command line is Makefile MCP's contract. Codex, Claude Code, LangChain, Cursor, and VS Code own their respective configuration formats and may change them independently. Treat the snippets below as integration examples and verify client-specific syntax against the corresponding client documentation when upgrading that client.

## Which presentation?

- `direct` (default): one typed MCP tool per callable `(context, target)` pair. Best for ordinary agent use and small/medium catalogs.
- `generic`: stable `list_tasks`, `describe_task`, and `run_task` tools. Useful for orchestration code or very large/dynamic catalogs.
- `both`: exposes both views of the same authorization/execution core. Use only when the client genuinely benefits from both.

For governed agent access, create `.makefile-mcp.yaml` before connecting the client. Auto mode intentionally exposes every conservatively discovered root target and is intended only for trusted local use.

## Codex

Add a stdio server to Codex configuration (normally `~/.codex/config.toml`):

```toml
[mcp_servers.makefile-mcp]
command = "makefile-mcp"
args = ["--root", "/absolute/path/to/repo", "serve", "--tools", "direct"]
```

Restart or reload the Codex session after changing MCP configuration.

## Claude Code

Add Makefile MCP as a stdio server:

```bash
claude mcp add makefile-mcp -- makefile-mcp --root /absolute/path/to/repo serve --tools direct
```

Choose Claude Code's project/user scope according to whether the configuration should travel with the repository or remain local to one machine.

## LangChain / LangGraph

Install LangChain's MCP adapter package in the orchestrator environment, then point it at the normal Makefile MCP CLI:

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient(
    {
        "makefile-mcp": {
            "transport": "stdio",
            "command": "makefile-mcp",
            "args": [
                "--root",
                "/absolute/path/to/repo",
                "serve",
                "--tools",
                "generic",
            ],
        }
    }
)

tools = await client.get_tools()
```

`generic` is shown because orchestration code often benefits from a stable MCP vocabulary. `direct` also works and preserves target-specific JSON schemas.

## Cursor

Create or update `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "makefile-mcp": {
      "type": "stdio",
      "command": "makefile-mcp",
      "args": [
        "--root",
        "/absolute/path/to/repo",
        "serve",
        "--tools",
        "direct"
      ]
    }
  }
}
```

Do not commit machine-specific absolute paths unless that is intentional for the repository.

## VS Code

Create or update `.vscode/mcp.json`:

```json
{
  "servers": {
    "makefile-mcp": {
      "type": "stdio",
      "command": "makefile-mcp",
      "args": [
        "--root",
        "/absolute/path/to/repo",
        "serve",
        "--tools",
        "direct"
      ]
    }
  }
}
```

## Using `uvx` instead of a persistent install

If the client can execute `uvx`, change the command to `uvx` and prepend the package/CLI name to the arguments:

```json
{
  "command": "uvx",
  "args": [
    "makefile-mcp",
    "--root",
    "/absolute/path/to/repo",
    "serve",
    "--tools",
    "direct"
  ]
}
```

A persistent `pipx install makefile-mcp` or `uv tool install makefile-mcp` avoids startup package-resolution work and is preferable for regular use.

## Troubleshooting

Verify the exact server command outside the client first:

```bash
makefile-mcp --root /absolute/path/to/repo doctor
makefile-mcp --root /absolute/path/to/repo list
```

If `.makefile-mcp.yaml` or the direct-tool inventory changes, restart the MCP server. Policy changes deliberately fail closed until restart.

Treat the MCP server command as executable configuration: review repository Makefiles and governed exposure before allowing an agent to invoke them.
