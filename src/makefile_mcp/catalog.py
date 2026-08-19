"""Resolve contexts and build the authorized public task catalog."""

from dataclasses import dataclass
from pathlib import Path

from makefile_mcp.errors import ContextNotFound, MakeInspectionError, TaskNotExposed, TaskNotFound
from makefile_mcp.filesystem import Fingerprint, ensure_within_root, fingerprint
from makefile_mcp.makefile import StaticMakeInspector
from makefile_mcp.models import MakefileMcpConfig, ProjectContext, TaskDefinition, TaskRisk


def _fingerprint(paths: list[Path]) -> Fingerprint:
    """Normalize filesystem fingerprint failures into the discovery error boundary."""
    try:
        return fingerprint(paths)
    except (OSError, RuntimeError) as exc:
        raise MakeInspectionError(f"could not fingerprint Make discovery inputs: {exc}") from exc


class Contexts:
    """Resolve configured context names to confined repository directories."""

    def __init__(self, root: Path, config: MakefileMcpConfig):
        """Create a context resolver for one repository/configuration pair."""
        self.root = root
        self.config = config

    def resolve(self, name: str = "root") -> ProjectContext:
        """Resolve one context name to a repository-confined directory."""
        if name == "root":
            return ProjectContext(directory=self.root)
        spec = self.config.contexts.get(name)
        if spec is None:
            raise ContextNotFound(f"unknown context: {name}")
        directory = ensure_within_root(self.root, self.root / spec.directory, must_exist=True)
        if not directory.is_dir():
            raise ContextNotFound(f"context is not a directory: {name}")
        return ProjectContext(directory=directory)

    def names(self) -> list[str]:
        """Return ``root`` plus configured context names in stable order."""
        return ["root", *sorted(self.config.contexts)]


@dataclass(frozen=True)
class CatalogSnapshot:
    """Cached discovery/exposure view for one context."""

    tasks: dict[str, TaskDefinition]
    discovered_targets: set[str]
    warnings: list[str]
    tracked_files: list[Path]


class Catalog:
    """Cache Make discovery and apply auto/governed exposure policy."""

    def __init__(
        self,
        *,
        config: MakefileMcpConfig,
        contexts: Contexts,
        inspector: StaticMakeInspector,
        governed: bool,
    ):
        """Create a catalog over one immutable configuration/exposure mode."""
        self.config = config
        self.contexts = contexts
        self.inspector = inspector
        self.governed = governed
        self._cache: dict[str, tuple[Fingerprint, CatalogSnapshot]] = {}

    def snapshot(self, context_name: str = "root") -> CatalogSnapshot:
        """Return the current cached-or-refreshed catalog snapshot for one context."""
        context = self.contexts.resolve(context_name)
        base_paths = [context.directory / "Makefile"]
        cached = self._cache.get(context_name)
        if cached and cached[0] == _fingerprint(base_paths + cached[1].tracked_files):
            return cached[1]

        raw = self.inspector.discover(directory=context.directory)
        tasks: dict[str, TaskDefinition] = {}
        for name, target in raw.targets.items():
            if not self.governed:
                # Auto mode mirrors lightweight Makefile MCP servers: every target our conservative
                # inspector can identify is callable. Inputs stay parameterless because there is
                # no operator-declared variable contract.
                tasks[name] = TaskDefinition(
                    name=name,
                    description=target.description,
                    context=context_name,
                    risk=TaskRisk.UNKNOWN,
                    timeout_seconds=self.config.defaults.timeout_seconds,
                )
                continue

            task_config = self.config.tasks.get(name)
            # Governed mode is deny-by-default. Discovery is broader than authorization and a
            # target is public only when config enables it for this exact context.
            if (
                task_config is None
                or not task_config.enabled
                or context_name not in task_config.contexts
            ):
                continue

            timeout = task_config.timeout_seconds or self.config.defaults.timeout_seconds
            tasks[name] = TaskDefinition(
                name=name,
                description=task_config.description or target.description,
                context=context_name,
                risk=task_config.risk or TaskRisk.UNKNOWN,
                timeout_seconds=timeout,
                variables=task_config.variables,
            )

        snapshot = CatalogSnapshot(
            tasks=tasks,
            discovered_targets=set(raw.targets),
            warnings=raw.warnings,
            tracked_files=[Path(path) for path in raw.tracked_files],
        )
        self._cache[context_name] = (_fingerprint(base_paths + snapshot.tracked_files), snapshot)
        return snapshot

    def list(self, context: str = "root") -> list[TaskDefinition]:
        """Return callable tasks in one context, sorted by target name."""
        tasks = self.snapshot(context).tasks
        return [tasks[name] for name in sorted(tasks)]

    def describe(self, task: str, context: str = "root") -> TaskDefinition:
        """Return one callable task or distinguish hidden from unknown targets."""
        snapshot = self.snapshot(context)
        definition = snapshot.tasks.get(task)
        if definition:
            return definition
        if task in snapshot.discovered_targets:
            raise TaskNotExposed(f"target exists but is not exposed in context {context!r}: {task}")
        raise TaskNotFound(f"unknown Make target: {task}")

    def resolve_capability(self, capability: str, context: str = "root") -> TaskDefinition:
        """Resolve a semantic capability name to a callable target in one context."""
        target = self.config.capabilities.get(capability)
        if not target:
            raise TaskNotFound(f"unknown capability: {capability}")
        return self.describe(target, context)
