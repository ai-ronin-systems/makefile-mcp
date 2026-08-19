import ast
import importlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[2] / "src" / "make_mcp"
PROJECT_ROOT = ROOT.parents[1]


def imports(path: Path) -> set[str]:
    """Return absolute import module names referenced by one Python source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def _module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    parts = ["make_mcp", *relative.parts]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def test_models_and_errors_do_not_depend_on_interfaces_or_execution():
    forbidden = (
        "mcp",
        "typer",
        "yaml",
        "make_mcp.cli",
        "make_mcp.mcp",
        "make_mcp.process",
        "make_mcp.execution",
    )
    violations = []
    for path in [ROOT / "models.py", ROOT / "errors.py"]:
        for name in imports(path):
            if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden):
                violations.append((path, name))
    assert not violations


def test_cli_and_mcp_presentations_do_not_create_subprocesses():
    paths = [ROOT / "cli.py", *sorted((ROOT / "mcp").glob("*.py"))]
    violations = []
    for path in paths:
        for name in imports(path):
            if name in {"asyncio.subprocess", "subprocess"}:
                violations.append((path, name))
    assert not violations


def test_obsolete_package_layers_and_mcp_modules_are_not_shipped():
    assert not (ROOT / "core").exists()
    assert not (ROOT / "infrastructure").exists()
    assert not (ROOT / "mcp_server.py").exists()
    assert not (ROOT / "mcp_tools.py").exists()


def test_raw_subprocess_creation_is_confined_to_process_module():
    hits: list[Path] = []
    for path in ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "create_subprocess_exec":
                hits.append(path)
    assert hits == [ROOT / "process.py"]


def test_all_shipped_internal_modules_import():
    # The server adapter requires the MCP SDK; presentation derivation intentionally does not.
    skip_mcp_server = importlib.util.find_spec("mcp") is None
    failures: list[tuple[str, str]] = []
    for path in sorted(ROOT.rglob("*.py")):
        module = _module_name(path)
        if module == "make_mcp":
            continue
        if skip_mcp_server and module == "make_mcp.mcp.server":
            continue
        try:
            importlib.import_module(module)
        except Exception as exc:  # pragma: no cover - assertion reports exact module/error
            failures.append((module, f"{type(exc).__name__}: {exc}"))
    assert not failures


def test_public_code_artifacts_have_docstrings():
    missing: list[str] = []
    for path in sorted(ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = _module_name(path)
        for node in tree.body:
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            if ast.get_docstring(node) is None:
                missing.append(f"{module}:{node.name}")
            if isinstance(node, ast.ClassDef):
                for member in node.body:
                    if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    if member.name.startswith("_"):
                        continue
                    if ast.get_docstring(member) is None:
                        missing.append(f"{module}:{node.name}.{member.name}")
    assert not missing


def test_patch_delivery_artifacts_are_not_shipped_in_product_tree():
    for relative in (
        "apply.sh",
        "PATCH_NOTES.md",
        "docs/hardening-2026-08-19.md",
        "docs/design-decisions.md",
    ):
        assert not (PROJECT_ROOT / relative).exists()


def test_mcp_presentation_does_not_depend_on_mcp_sdk():
    # Direct tool derivation stays independently testable and never owns transport policy.
    assert all(
        not (name == "mcp" or name.startswith("mcp."))
        for name in imports(ROOT / "mcp" / "presentation.py")
    )


def test_package_version_has_one_source():
    import tomllib

    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in data["project"]
    assert data["project"]["dynamic"] == ["version"]
    assert data["tool"]["hatch"]["version"]["path"] == "src/make_mcp/version.py"


def test_github_actions_are_pinned_to_immutable_commits():
    import re

    sha_ref = re.compile(r"^[0-9a-f]{40}$")
    violations: list[str] = []
    for workflow in sorted((PROJECT_ROOT / ".github" / "workflows").glob("*.yml")):
        for line_number, line in enumerate(workflow.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("- uses:"):
                action = stripped.removeprefix("- uses:").strip().split(" #", 1)[0]
            elif stripped.startswith("uses:"):
                action = stripped.removeprefix("uses:").strip().split(" #", 1)[0]
            else:
                continue
            if action.startswith("./"):
                continue
            _, separator, ref = action.rpartition("@")
            if not separator or not sha_ref.fullmatch(ref):
                violations.append(f"{workflow.name}:{line_number}: {action}")
    assert not violations
