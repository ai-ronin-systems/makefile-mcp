"""Static Makefile discovery without evaluating recipes or invoking a shell."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from make_mcp.errors import MakeInspectionError

_TARGET_LINE = re.compile(r"^([^#\t ][^:=]*?):(?:\s.*)?$")
_INCLUDE = re.compile(r"^-?include\s+(.+)$")
_VALID_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@/+:-]*$")


@dataclass
class RawMakeTarget:
    name: str
    description: str | None = None
    phony: bool = False


@dataclass
class RawMakeCatalog:
    targets: dict[str, RawMakeTarget] = field(default_factory=dict)
    source_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _description(line: str) -> str | None:
    if "##" not in line:
        return None
    text = line.split("##", 1)[1].strip()
    return text or None


def _target_names(lhs: str) -> list[str]:
    return [
        name
        for name in lhs.split()
        if not name.startswith(".")
        and "%" not in name
        and "$" not in name
        and _VALID_TARGET.fullmatch(name)
    ]


def parse_makefiles(makefile: Path, *, repository_root: Path) -> RawMakeCatalog:
    targets: dict[str, RawMakeTarget] = {}
    warnings: list[str] = []
    source_files: list[str] = []
    pending = [makefile.resolve()]
    seen: set[Path] = set()
    phony_names: set[str] = set()

    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            current.relative_to(repository_root)
        except ValueError:
            warnings.append(f"ignored included Makefile outside repository: {current}")
            continue
        if not current.exists():
            warnings.append(f"included Makefile does not exist: {current}")
            continue

        source_files.append(str(current))
        for raw_line in current.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.rstrip()
            if not line or line.startswith("\t") or line.lstrip().startswith("#"):
                continue

            include = _INCLUDE.match(line.strip())
            if include:
                for token in include.group(1).split():
                    if "$" in token or "%" in token:
                        warnings.append(f"dynamic include not tracked: {token}")
                        continue
                    child = (current.parent / token).resolve()
                    try:
                        child.relative_to(repository_root)
                    except ValueError:
                        warnings.append(f"ignored included Makefile outside repository: {child}")
                    else:
                        pending.append(child)
                continue

            if line.startswith(".PHONY:"):
                phony_names.update(line.split(":", 1)[1].split())
                continue

            match = _TARGET_LINE.match(line)
            if not match:
                continue
            for name in _target_names(match.group(1)):
                desc = _description(line)
                existing = targets.get(name)
                if existing is None:
                    targets[name] = RawMakeTarget(name=name, description=desc)
                elif desc and not existing.description:
                    existing.description = desc

    for name in phony_names:
        target = targets.get(name)
        if target:
            target.phony = True
        elif _VALID_TARGET.fullmatch(name):
            targets[name] = RawMakeTarget(name=name, phony=True)

    return RawMakeCatalog(targets=targets, source_files=source_files, warnings=warnings)


class StaticMakeInspector:
    def __init__(self, repository_root: Path):
        self._repository_root = repository_root.resolve()

    def discover(self, *, directory: Path, makefile: Path | None = None) -> RawMakeCatalog:
        candidate = makefile or (directory / "Makefile")
        if not candidate.is_absolute():
            candidate = directory / candidate
        candidate = candidate.resolve()
        if not candidate.exists():
            raise MakeInspectionError(f"Makefile not found: {candidate}")
        return parse_makefiles(candidate, repository_root=self._repository_root)
