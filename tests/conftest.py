from pathlib import Path

import pytest

from makefile_mcp.app import build_application


@pytest.fixture
def repo(tmp_path: Path):
    def create(makefile: str, config: str | None = None) -> Path:
        (tmp_path / "Makefile").write_text(makefile, encoding="utf-8")
        if config is not None:
            (tmp_path / ".makefile-mcp.yaml").write_text(config, encoding="utf-8")
        return tmp_path

    return create


@pytest.fixture
def app_for(repo):
    def create(makefile: str, config: str | None = None):
        return build_application(repo(makefile, config))

    return create
