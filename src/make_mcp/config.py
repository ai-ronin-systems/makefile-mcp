"""Load optional metadata-only Make MCP configuration."""

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from make_mcp.errors import ConfigurationError
from make_mcp.filesystem import Fingerprint, fingerprint
from make_mcp.models import MakeMcpConfig


@dataclass(frozen=True)
class LoadedConfig:
    """Validated repository policy together with its exposure-mode decision."""

    config: MakeMcpConfig
    governed: bool
    policy_fingerprint: Fingerprint


def load_config_state(repository_root: Path) -> LoadedConfig:
    """Load repository policy and decide auto/governed mode from one filesystem observation.

    Args:
        repository_root: Detected trusted repository root.

    Returns:
        Validated configuration, exposure mode, and the policy-file fingerprint used by the
        application to fail closed if authorization policy changes while it is running.

    Raises:
        ConfigurationError: If the policy file exists but cannot be parsed or validated, or if
            it changes while being loaded.
    """
    path = repository_root / ".make-mcp.yaml"
    try:
        before = fingerprint([path])
        if not path.exists():
            after = fingerprint([path])
            if before != after:
                raise ConfigurationError(".make-mcp.yaml changed while configuration was loaded")
            return LoadedConfig(
                config=MakeMcpConfig(),
                governed=False,
                policy_fingerprint=after,
            )
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        after = fingerprint([path])
        if before != after:
            raise ConfigurationError(".make-mcp.yaml changed while configuration was loaded")
        if not isinstance(raw, dict):
            raise ConfigurationError(".make-mcp.yaml must contain a mapping")
        return LoadedConfig(
            config=MakeMcpConfig.model_validate(raw),
            governed=True,
            policy_fingerprint=after,
        )
    except ConfigurationError:
        raise
    except (OSError, RuntimeError, yaml.YAMLError, ValidationError) as exc:
        raise ConfigurationError(f"invalid .make-mcp.yaml: {exc}") from exc


def load_config(repository_root: Path) -> MakeMcpConfig:
    """Load only the validated repository configuration.

    This compatibility convenience delegates to :func:`load_config_state`; the application
    composition root uses the state form so config contents and exposure mode share one source.
    """
    return load_config_state(repository_root).config
