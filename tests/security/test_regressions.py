from pathlib import Path

import pytest

from make_mcp.infrastructure.filesystem import FileContextLock
from make_mcp.errors import TaskBusyError


def test_shell_true_never_used():
    source_root = Path(__file__).parents[2] / "src"
    hits = []
    for path in source_root.rglob("*.py"):
        if "shell=True" in path.read_text(encoding="utf-8"):
            hits.append(path)
    assert not hits


def test_context_lock_is_non_blocking(tmp_path: Path):
    lock = FileContextLock(tmp_path)
    with lock.acquire("root"):
        with pytest.raises(TaskBusyError):
            with lock.acquire("root"):
                pass
