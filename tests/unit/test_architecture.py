import ast
from pathlib import Path

ROOT = Path(__file__).parents[2] / "src" / "make_mcp"


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_models_and_errors_do_not_depend_on_interfaces_or_infrastructure():
    forbidden = ("mcp", "typer", "yaml", "make_mcp.infrastructure", "make_mcp.mcp_server", "make_mcp.cli")
    violations = []
    for path in [ROOT / "models.py", ROOT / "errors.py"]:
        for name in imports(path):
            if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden):
                violations.append((path, name))
    assert not violations


def test_core_does_not_depend_on_cli_or_mcp():
    violations = []
    for path in (ROOT / "core").rglob("*.py"):
        for name in imports(path):
            if name in {"typer", "mcp"} or name.startswith(("mcp.", "make_mcp.cli", "make_mcp.mcp_server")):
                violations.append((path, name))
    assert not violations
