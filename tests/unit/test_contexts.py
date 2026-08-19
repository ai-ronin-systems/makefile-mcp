from pathlib import Path

import pytest

from makefile_mcp.catalog import Contexts
from makefile_mcp.errors import UnsafePathError
from makefile_mcp.filesystem import detect_repository_root
from makefile_mcp.models import ContextConfig, MakefileMcpConfig


def test_context_must_stay_in_root(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-other"
    outside.mkdir()
    config = MakefileMcpConfig(contexts={"bad": ContextConfig(directory="../" + outside.name)})
    contexts = Contexts(tmp_path, config)
    with pytest.raises(UnsafePathError):
        contexts.resolve("bad")


def test_root_detection_prefers_repo_config_over_nested_makefile(tmp_path: Path):
    (tmp_path / ".makefile-mcp.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    nested = tmp_path / "backend"
    nested.mkdir()
    (nested / "Makefile").write_text("test:\n\t@true\n", encoding="utf-8")
    assert detect_repository_root(nested) == tmp_path


def test_root_detection_prefers_nearest_repository_boundary(tmp_path: Path):
    # A parent policy file must not capture execution launched from a nested Git repo.
    (tmp_path / ".makefile-mcp.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    child = tmp_path / "child"
    child.mkdir()
    (child / ".git").mkdir()
    (child / "Makefile").write_text("test:\n\t@true\n", encoding="utf-8")
    nested = child / "src"
    nested.mkdir()
    assert detect_repository_root(nested) == child
