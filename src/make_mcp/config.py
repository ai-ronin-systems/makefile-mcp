"""Load metadata-only Make MCP configuration."""

from pathlib import Path

import yaml
from pydantic import ValidationError

from make_mcp.errors import ConfigurationError
from make_mcp.models import MakeMcpConfig


def load_config(repository_root: Path) -> MakeMcpConfig:
    path = repository_root / ".make-mcp.yaml"
    if not path.exists():
        return MakeMcpConfig()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ConfigurationError(".make-mcp.yaml must contain a mapping")
        return MakeMcpConfig.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ConfigurationError(f"invalid .make-mcp.yaml: {exc}") from exc
