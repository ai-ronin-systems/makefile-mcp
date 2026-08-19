#!/usr/bin/env python3
"""Validate Makefile MCP release identity and built distribution metadata."""

from __future__ import annotations

import argparse
import json
import re
import runpy
import tarfile
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "src" / "makefile_mcp" / "version.py"
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"
README = ROOT / "README.md"
SERVER_JSON = ROOT / "server.json"
MCP_REGISTRY_NAME = "io.github.ai-ronin-systems/makefile-mcp"
ALLOWED_DIST_HOUSEKEEPING = {".gitignore"}
TAG_RE = re.compile(r"^v(?P<version>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))$")


def package_version() -> str:
    """Return the single-source package version without importing runtime dependencies."""
    value = runpy.run_path(str(VERSION_FILE)).get("__version__")
    if not isinstance(value, str) or not value:
        raise ValueError(f"{VERSION_FILE} does not define a non-empty __version__")
    return value


def project_name() -> str:
    """Return the canonical project name from pyproject metadata."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return str(data["project"]["name"])


def validate_tag(tag: str, version: str) -> None:
    """Require a stable vX.Y.Z tag that exactly matches the package version."""
    match = TAG_RE.fullmatch(tag)
    if match is None:
        raise ValueError(f"release tag must use stable vX.Y.Z form, got {tag!r}")
    if match.group("version") != version:
        raise ValueError(f"tag {tag!r} does not match package version {version!r}")


def validate_changelog(version: str) -> None:
    """Require an empty Unreleased section and a dated section for this version."""
    text = CHANGELOG.read_text(encoding="utf-8")
    marker = "## Unreleased"
    if marker not in text:
        raise ValueError("CHANGELOG.md is missing the '## Unreleased' section")
    after = text.split(marker, 1)[1]
    unreleased, separator, _ = after.partition("\n## ")
    if not separator:
        raise ValueError("CHANGELOG.md has no released section after '## Unreleased'")
    if unreleased.strip():
        raise ValueError("CHANGELOG.md has unreleased entries; cut the release before tagging")
    release_heading = rf"^## {re.escape(version)} — \d{{4}}-\d{{2}}-\d{{2}}$"
    if re.search(release_heading, text, re.MULTILINE) is None:
        raise ValueError(f"CHANGELOG.md has no dated section for {version}")


def validate_mcp_registry_metadata(expected_name: str, expected_version: str) -> None:
    """Keep MCP Registry metadata aligned with the releasable Python package."""
    data = json.loads(SERVER_JSON.read_text(encoding="utf-8"))
    if data.get("name") != MCP_REGISTRY_NAME:
        raise ValueError(
            f"server.json name must be {MCP_REGISTRY_NAME!r}, got {data.get('name')!r}"
        )
    if data.get("version") != expected_version:
        raise ValueError(
            f"server.json version {data.get('version')!r} does not match {expected_version!r}"
        )
    repository = data.get("repository")
    if (
        not isinstance(repository, dict)
        or repository.get("url") != "https://github.com/ai-ronin-systems/makefile-mcp"
        or repository.get("source") != "github"
    ):
        raise ValueError(
            "server.json repository metadata does not identify the canonical GitHub repository"
        )
    packages = data.get("packages")
    if not isinstance(packages, list) or len(packages) != 1 or not isinstance(packages[0], dict):
        raise ValueError("server.json must define exactly one PyPI package")
    package = packages[0]
    if package.get("registryType") != "pypi" or package.get("identifier") != expected_name:
        raise ValueError("server.json package must identify the makefile-mcp PyPI distribution")
    if package.get("version") != expected_version:
        raise ValueError(
            f"server.json package version {package.get('version')!r} does not match "
            f"{expected_version!r}"
        )
    if package.get("transport") != {"type": "stdio"}:
        raise ValueError("server.json package transport must be stdio")
    arguments = package.get("packageArguments")
    if arguments != [{"type": "positional", "value": "serve"}]:
        raise ValueError(
            "server.json package arguments must start Makefile MCP with the serve command"
        )
    ownership_marker = f"mcp-name: {MCP_REGISTRY_NAME}"
    if ownership_marker not in README.read_text(encoding="utf-8"):
        raise ValueError(f"README.md is missing MCP Registry ownership marker {ownership_marker!r}")


def _metadata_fields(text: str) -> tuple[str, str]:
    message = Parser().parsestr(text)
    name = message.get("Name")
    version = message.get("Version")
    if not name or not version:
        raise ValueError("distribution metadata is missing Name or Version")
    return name, version


def _wheel_metadata(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as archive:
        candidates = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(candidates) != 1:
            raise ValueError(
                f"{path.name}: expected one wheel METADATA file, found {len(candidates)}"
            )
        return _metadata_fields(archive.read(candidates[0]).decode("utf-8"))


def _sdist_metadata(path: Path) -> tuple[str, str]:
    with tarfile.open(path, mode="r:gz") as archive:
        candidates = [
            member for member in archive.getmembers() if member.name.endswith("/PKG-INFO")
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"{path.name}: expected one sdist PKG-INFO file, found {len(candidates)}"
            )
        extracted = archive.extractfile(candidates[0])
        if extracted is None:
            raise ValueError(f"{path.name}: could not read PKG-INFO")
        return _metadata_fields(extracted.read().decode("utf-8"))


def validate_distributions(dist: Path, expected_name: str, expected_version: str) -> None:
    """Require exactly one wheel and one sdist with matching embedded metadata."""
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    unexpected = sorted(
        path.name
        for path in dist.iterdir()
        if path.is_file()
        and path not in {*wheels, *sdists}
        and path.name not in ALLOWED_DIST_HOUSEKEEPING
    )
    if len(wheels) != 1 or len(sdists) != 1 or unexpected:
        raise ValueError(
            "dist/ must contain exactly one wheel and one .tar.gz sdist; "
            f"found wheels={len(wheels)}, sdists={len(sdists)}, unexpected={unexpected}"
        )
    for path, metadata_reader in ((wheels[0], _wheel_metadata), (sdists[0], _sdist_metadata)):
        name, version = metadata_reader(path)
        if name != expected_name or version != expected_version:
            raise ValueError(
                f"{path.name}: metadata is {name} {version}, expected "
                f"{expected_name} {expected_version}"
            )


def main() -> int:
    """Run release checks and return a process exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Git tag to validate, for example v0.1.0")
    parser.add_argument(
        "--dist", type=Path, help="Optional built distribution directory to inspect"
    )
    args = parser.parse_args()

    try:
        version = package_version()
        name = project_name()
        validate_tag(args.tag, version)
        validate_changelog(version)
        validate_mcp_registry_metadata(name, version)
        if args.dist is not None:
            validate_distributions(args.dist.resolve(), name, version)
    except (
        json.JSONDecodeError,
        KeyError,
        OSError,
        ValueError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as exc:
        print(f"release-check: error: {exc}")
        return 2

    detail = f"; dist={args.dist}" if args.dist is not None else ""
    print(f"release-check: ok: {args.tag} -> {name} {version}{detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
