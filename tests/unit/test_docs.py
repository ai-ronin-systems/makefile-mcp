"""Cheap documentation regressions for public contracts and local navigation."""

import re
from pathlib import Path

from makefile_mcp.mcp.presentation import McpPresentation

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_DOCS = {
    "README.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "docs/architecture.md",
    "docs/design_rationale.md",
    "docs/cli.md",
    "docs/configuration.md",
    "docs/discovery.md",
    "docs/governed_mode.md",
    "docs/mcp_presentations.md",
    "docs/contexts_and_capabilities.md",
    "docs/clients.md",
    "docs/security.md",
    "docs/deployment.md",
    "docs/development.md",
    "docs/releasing.md",
}
_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_CLI_COMMAND = re.compile(r'@cli\.command\("([a-z0-9_-]+)"\)')


def _markdown_files() -> list[Path]:
    roots = [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "SECURITY.md",
        PROJECT_ROOT / "CONTRIBUTING.md",
        *sorted((PROJECT_ROOT / "docs").rglob("*.md")),
        *sorted((PROJECT_ROOT / "examples").rglob("README.md")),
    ]
    return [path for path in roots if path.is_file()]


def _slug(heading: str) -> str:
    """Approximate GitHub Markdown anchors for the simple headings used by Makefile MCP docs."""
    value = re.sub(r"[`*_~]", "", heading).strip().lower()
    value = re.sub(r"[^\w\- ]", "", value)
    return re.sub(r"\s+", "-", value)


def _anchors(path: Path) -> set[str]:
    return {
        _slug(match.group(1))
        for line in path.read_text(encoding="utf-8").splitlines()
        if (match := _HEADING.match(line))
    }


def test_canonical_documents_exist():
    missing = sorted(path for path in CANONICAL_DOCS if not (PROJECT_ROOT / path).is_file())
    assert missing == []


def test_relative_markdown_links_and_local_anchors_resolve():
    problems: list[str] = []
    for source in _markdown_files():
        text = source.read_text(encoding="utf-8")
        for target in _LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            target_path, _, fragment = target.partition("#")
            destination = source if not target_path else (source.parent / target_path).resolve()
            if not destination.is_file():
                problems.append(f"{source.relative_to(PROJECT_ROOT)} -> missing {target}")
                continue
            if fragment and fragment not in _anchors(destination):
                problems.append(
                    f"{source.relative_to(PROJECT_ROOT)} -> missing anchor #{fragment} in "
                    f"{destination.relative_to(PROJECT_ROOT)}"
                )
    assert problems == []


def test_public_markdown_has_no_empty_list_items_or_legacy_product_names():
    legacy_names = (
        "Just " + "Make It " + "MCP",
        "J" + "MIM",
        "make" + "-mcp",
        "make" + "_mcp",
        "MAKE" + "_MCP",
        ".make" + "-mcp",
    )
    problems: list[str] = []
    for path in _markdown_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip() in {"-", "*", "+"}:
                problems.append(f"{path.relative_to(PROJECT_ROOT)}:{number}: empty list item")
            for legacy_name in legacy_names:
                if legacy_name in line:
                    problems.append(
                        f"{path.relative_to(PROJECT_ROOT)}:{number}: legacy product name "
                        f"{legacy_name!r}"
                    )
    assert problems == []


def test_cli_reference_covers_every_public_cli_command():
    cli_source = (PROJECT_ROOT / "src/makefile_mcp/cli.py").read_text(encoding="utf-8")
    documented = (PROJECT_ROOT / "docs/cli.md").read_text(encoding="utf-8")
    commands = set(_CLI_COMMAND.findall(cli_source))
    assert commands == {"list", "describe", "run", "doctor", "serve"}
    assert all(f"## `{command}`" in documented for command in commands)


def test_documented_mcp_presentations_match_runtime_enum():
    documented = (PROJECT_ROOT / "docs/mcp_presentations.md").read_text(encoding="utf-8")
    values = {item.value for item in McpPresentation}
    assert values == {"direct", "generic", "both"}
    assert all(value in documented for value in values)


def test_configuration_reference_tracks_schema_version_one():
    documented = (PROJECT_ROOT / "docs/configuration.md").read_text(encoding="utf-8")
    assert "Current schema version: `1`." in documented
