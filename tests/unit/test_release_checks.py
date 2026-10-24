import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from makefile_mcp.version import __version__ as VERSION

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "check_release.py"


def _released_changelog() -> str:
    """Return the repository changelog as it reads at release time: Unreleased emptied."""
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return re.sub(r"## Unreleased\n.*?(?=\n## )", "## Unreleased\n", text, count=1, flags=re.S)


def _run_release_check(
    *args: str, changelog: str | None = None
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "CHANGELOG.md"
        path.write_text(_released_changelog() if changelog is None else changelog, "utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=ROOT,
            env={**os.environ, "RELEASE_CHECK_CHANGELOG": str(path)},
            capture_output=True,
            text=True,
            check=False,
        )


def _write_fake_distributions(dist: Path, version: str = VERSION) -> None:
    metadata = f"Metadata-Version: 2.4\nName: makefile-mcp\nVersion: {version}\n\n"
    wheel = dist / f"makefile_mcp-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, mode="w") as archive:
        archive.writestr(f"makefile_mcp-{version}.dist-info/METADATA", metadata)

    sdist = dist / f"makefile_mcp-{version}.tar.gz"
    payload = metadata.encode("utf-8")
    with tarfile.open(sdist, mode="w:gz") as archive:
        info = tarfile.TarInfo(name=f"makefile_mcp-{version}/PKG-INFO")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))


def test_release_check_accepts_repository_release_identity():
    result = _run_release_check("--tag", f"v{VERSION}")

    assert result.returncode == 0
    assert "release-check: ok" in result.stdout


def test_release_check_rejects_unreleased_changelog_entries():
    changelog = _released_changelog().replace("## Unreleased\n", "## Unreleased\n\n- pending\n")
    result = _run_release_check("--tag", f"v{VERSION}", changelog=changelog)

    assert result.returncode == 2
    assert "unreleased entries" in result.stdout


def test_release_check_rejects_tag_version_mismatch():
    result = _run_release_check("--tag", "v0.1.1")

    assert result.returncode == 2
    assert "does not match package version" in result.stdout


def test_release_check_validates_built_distribution_metadata(tmp_path: Path):
    _write_fake_distributions(tmp_path)

    result = _run_release_check("--tag", f"v{VERSION}", "--dist", str(tmp_path))

    assert result.returncode == 0


def test_release_check_accepts_uv_build_gitignore(tmp_path: Path):
    _write_fake_distributions(tmp_path)
    (tmp_path / ".gitignore").write_text("*\n", encoding="utf-8")

    result = _run_release_check("--tag", f"v{VERSION}", "--dist", str(tmp_path))

    assert result.returncode == 0


def test_release_check_rejects_unexpected_distribution_files(tmp_path: Path):
    _write_fake_distributions(tmp_path)
    (tmp_path / "unexpected.txt").write_text("junk\n", encoding="utf-8")

    result = _run_release_check("--tag", f"v{VERSION}", "--dist", str(tmp_path))

    assert result.returncode == 2
    assert "unexpected=['unexpected.txt']" in result.stdout


def test_release_check_rejects_mismatched_distribution_metadata(tmp_path: Path):
    _write_fake_distributions(tmp_path, version="9.9.9")

    result = _run_release_check("--tag", f"v{VERSION}", "--dist", str(tmp_path))

    assert result.returncode == 2
    assert f"expected makefile-mcp {VERSION}" in result.stdout
