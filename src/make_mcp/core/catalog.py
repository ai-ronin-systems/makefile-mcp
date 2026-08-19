"""Resolve contexts and build the authorized public task catalog."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from make_mcp.errors import ContextNotFound, TaskNotExposed, TaskNotFound
from make_mcp.infrastructure.filesystem import ensure_within_root, fingerprint
from make_mcp.infrastructure.make import RawMakeCatalog
from make_mcp.models import MakeMcpConfig, ProjectContext, TaskDefinition, TaskRisk, TaskVariable

_DANGEROUS_WORDS = {"destroy", "delete", "drop", "purge", "reset", "wipe"}
_WRITE_WORDS = {"build", "clean", "deploy", "format", "install", "package", "publish", "release"}


class MakeInspector(Protocol):
    def discover(self, *, directory: Path, makefile: Path | None = None) -> RawMakeCatalog: ...


def infer_risk(task_name: str) -> TaskRisk:
    words = {part.lower() for part in task_name.replace("_", "-").split("-")}
    if words & _DANGEROUS_WORDS:
        return TaskRisk.DANGEROUS
    if words & _WRITE_WORDS:
        return TaskRisk.WRITE
    return TaskRisk.SAFE


def _variables_from_config(task_config) -> dict[str, TaskVariable]:
    if task_config is None:
        return {}
    return {
        name: TaskVariable.model_validate(spec.model_dump())
        for name, spec in task_config.variables.items()
    }


class Contexts:
    def __init__(self, root: Path, config: MakeMcpConfig):
        self.root = root
        self.config = config

    def resolve(self, name: str = "root") -> ProjectContext:
        if name == "root":
            return ProjectContext(name="root", directory=self.root)
        spec = self.config.contexts.get(name)
        if spec is None:
            raise ContextNotFound(f"unknown context: {name}")
        directory = ensure_within_root(self.root, self.root / spec.directory, must_exist=True)
        if not directory.is_dir():
            raise ContextNotFound(f"context is not a directory: {name}")
        return ProjectContext(name=name, directory=directory)

    def names(self) -> list[str]:
        return ["root", *sorted(self.config.contexts)]


@dataclass(frozen=True)
class CatalogSnapshot:
    tasks: dict[str, TaskDefinition]
    discovered_targets: set[str]
    warnings: list[str]
    source_files: list[Path]


class Catalog:
    """Cache Make discovery and apply public exposure policy."""

    def __init__(
        self,
        *,
        root: Path,
        config: MakeMcpConfig,
        contexts: Contexts,
        inspector: MakeInspector,
    ):
        self.root = root
        self.config = config
        self.contexts = contexts
        self.inspector = inspector
        self._cache: dict[str, tuple[tuple[tuple[str, int, int], ...], CatalogSnapshot]] = {}

    def snapshot(self, context_name: str = "root") -> CatalogSnapshot:
        context = self.contexts.resolve(context_name)
        base_paths = [context.directory / "Makefile", self.root / ".make-mcp.yaml"]
        cached = self._cache.get(context_name)
        if cached and cached[0] == fingerprint(base_paths + cached[1].source_files):
            return cached[1]

        raw = self.inspector.discover(directory=context.directory)
        tasks: dict[str, TaskDefinition] = {}
        for name, target in raw.targets.items():
            task_config = self.config.tasks.get(name)
            if task_config is not None and not task_config.enabled:
                continue
            if task_config is not None:
                source = "config"
            elif target.description:
                source = "documented"
            elif target.phony:
                source = "phony"
            else:
                continue

            timeout = (
                task_config.timeout_seconds
                if task_config and task_config.timeout_seconds
                else self.config.defaults.timeout_seconds
            )
            tasks[name] = TaskDefinition(
                name=name,
                description=(
                    task_config.description
                    if task_config and task_config.description
                    else target.description
                ),
                context=context_name,
                risk=(task_config.risk if task_config and task_config.risk else infer_risk(name)),
                timeout_seconds=timeout,
                variables=_variables_from_config(task_config),
                exposure_source=source,
            )

        snapshot = CatalogSnapshot(
            tasks=tasks,
            discovered_targets=set(raw.targets),
            warnings=raw.warnings,
            source_files=[Path(path) for path in raw.source_files],
        )
        self._cache[context_name] = (fingerprint(base_paths + snapshot.source_files), snapshot)
        return snapshot

    def list(self, context: str = "root") -> list[TaskDefinition]:
        tasks = self.snapshot(context).tasks
        return [tasks[name] for name in sorted(tasks)]

    def describe(self, task: str, context: str = "root") -> TaskDefinition:
        snapshot = self.snapshot(context)
        definition = snapshot.tasks.get(task)
        if definition:
            return definition
        if task in snapshot.discovered_targets:
            raise TaskNotExposed(f"target exists but is not publicly exposed: {task}")
        raise TaskNotFound(f"unknown Make target: {task}")

    def resolve_capability(self, capability: str, context: str = "root") -> TaskDefinition:
        target = self.config.capabilities.get(capability)
        if not target:
            raise TaskNotFound(f"unknown capability: {capability}")
        return self.describe(target, context)
