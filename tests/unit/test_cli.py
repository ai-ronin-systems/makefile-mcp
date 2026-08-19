from typer.testing import CliRunner

from make_mcp.cli import cli
from make_mcp.version import __version__


def test_global_version_flag_reports_package_version_without_repository_bootstrap():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_run_preview_uses_make_dry_run(tmp_path):
    (tmp_path / "Makefile").write_text(
        ".PHONY: write\nwrite:\n\t@touch preview-marker\n", encoding="utf-8"
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["--root", str(tmp_path), "run", "write", "--preview"])

    assert result.exit_code == 0
    assert "[preview]" in result.stdout
    assert "touch preview-marker" in result.stdout
    assert not (tmp_path / "preview-marker").exists()
