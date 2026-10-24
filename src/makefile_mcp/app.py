"""Small composition root and protocol-agnostic application facade."""

import os
from dataclasses import dataclass
from pathlib import Path

from makefile_mcp.audit import AuditLog
from makefile_mcp.catalog import Catalog, Contexts
from makefile_mcp.config import load_config_state
from makefile_mcp.doctor import run_doctor
from makefile_mcp.errors import ConfigurationError, MakefileMcpError
from makefile_mcp.execution import Approver, TaskExecutor
from makefile_mcp.filesystem import (
    FileContextLock,
    Fingerprint,
    detect_repository_root,
    ensure_within_root,
    fingerprint,
)
from makefile_mcp.makefile import StaticMakeInspector
from makefile_mcp.models import DoctorResult, MakefileMcpConfig, TaskDefinition, TaskResult
from makefile_mcp.process import SubprocessRunner


@dataclass(frozen=True)
class Application:
    """Protocol-independent facade over catalog, diagnostics, and task execution."""

    root: Path
    config: MakefileMcpConfig
    contexts: Contexts
    catalog: Catalog
    executor: TaskExecutor
    governed: bool
    policy_fingerprint: Fingerprint
    # Pinned trusted files and their startup fingerprint; empty when nothing is pinned.
    pinned_paths: tuple[Path, ...] = ()
    pinned_fingerprint: Fingerprint = ()

    def _ensure_policy_current(self) -> None:
        """Fail closed if the policy or a pinned trusted file changed since startup."""
        try:
            current = fingerprint([self.root / ".makefile-mcp.yaml"])
            pinned = fingerprint(list(self.pinned_paths)) if self.pinned_paths else ()
        except (OSError, RuntimeError) as exc:
            raise ConfigurationError(f"could not verify .makefile-mcp.yaml state: {exc}") from exc
        if current != self.policy_fingerprint:
            raise ConfigurationError(
                ".makefile-mcp.yaml changed since startup; "
                "restart makefile-mcp to apply policy safely"
            )
        if pinned != self.pinned_fingerprint:
            raise ConfigurationError(
                "pinned Make sources changed since startup; "
                "review the change, then restart makefile-mcp to trust it"
            )

    def list_contexts(self) -> list[str]:
        """Return all configured execution-context names, including ``root``."""
        self._ensure_policy_current()
        return self.contexts.names()

    def list_tasks(self, context: str = "root") -> list[TaskDefinition]:
        """Return callable tasks for one context in stable name order."""
        self._ensure_policy_current()
        return self.catalog.list(context)

    def describe_task(self, task: str, context: str = "root") -> TaskDefinition:
        """Return the callable contract for one task/context pair."""
        self._ensure_policy_current()
        return self.catalog.describe(task, context)

    def resolve_capability(self, capability: str, context: str = "root") -> TaskDefinition:
        """Resolve a semantic capability to its callable task in one context."""
        self._ensure_policy_current()
        return self.catalog.resolve_capability(capability, context)

    def list_capabilities(self, context: str = "root") -> dict[str, str]:
        """Return capability mappings whose target is callable in one context."""
        self._ensure_policy_current()
        exposed = {task.name for task in self.catalog.list(context)}
        return {
            name: target for name, target in self.config.capabilities.items() if target in exposed
        }

    async def run_task(
        self,
        task: str,
        variables: dict[str, str] | None = None,
        context: str = "root",
        *,
        preview: bool = False,
        approve: Approver | None = None,
    ) -> TaskResult:
        """Execute or preview one callable task through the shared bounded executor.

        ``approve`` asks a human to confirm risky tasks; without it they are refused.
        """
        try:
            self._ensure_policy_current()
        except ConfigurationError as exc:
            # A tampered pin or policy is exactly what the audit log is for.
            self.executor.audit.refuse(task, context, variables or {}, reason=str(exc))
            raise
        return await self.executor.run(task, variables, context, preview=preview, approve=approve)

    def needs_approval(self, task: TaskDefinition) -> bool:
        """Return whether policy requires human approval before *task* runs."""
        return self.executor.needs_approval(task)

    def doctor(self) -> DoctorResult:
        """Run read-only diagnostics against repository, policy, and discovery state."""
        self._ensure_policy_current()
        return run_doctor(
            root=self.root,
            config=self.config,
            contexts=self.contexts,
            catalog=self.catalog,
            governed=self.governed,
        )


def build_application(start: Path | None = None, *, legacy_auto_run: bool = False) -> Application:
    """Compose one application instance rooted at *start* or the current directory.

    ``legacy_auto_run`` restores the pre-0.2 behavior where auto mode runs every target.
    """
    root = detect_repository_root(start or Path.cwd())
    loaded = load_config_state(root)
    contexts = Contexts(root, loaded.config)
    catalog = Catalog(
        config=loaded.config,
        contexts=contexts,
        inspector=StaticMakeInspector(root),
        governed=loaded.governed,
        legacy_auto_run=legacy_auto_run,
    )
    executor = TaskExecutor(
        root=root,
        config=loaded.config,
        contexts=contexts,
        catalog=catalog,
        runner=SubprocessRunner(),
        lock=FileContextLock(root),
        audit=AuditLog(root, loaded.config.audit),
    )
    pinned = _pinned_paths(root, loaded.config, contexts, catalog)
    try:
        pinned_fingerprint = fingerprint(list(pinned)) if pinned else ()
    except (OSError, RuntimeError) as exc:
        raise ConfigurationError(f"could not fingerprint pinned files: {exc}") from exc
    return Application(
        root=root,
        config=loaded.config,
        contexts=contexts,
        catalog=catalog,
        executor=executor,
        governed=loaded.governed,
        policy_fingerprint=loaded.policy_fingerprint,
        pinned_paths=pinned,
        pinned_fingerprint=pinned_fingerprint,
    )


def _pinned_paths(
    root: Path, config: MakefileMcpConfig, contexts: Contexts, catalog: Catalog
) -> tuple[Path, ...]:
    """Expand ``pin`` into the exact files and directories to fingerprint at startup."""
    if config.pin is None:
        return ()
    paths: list[Path] = []
    if config.pin.make_sources:
        for name in contexts.names():
            snapshot = catalog.snapshot(name)
            paths += [contexts.resolve(name).directory / "Makefile", *snapshot.tracked_files]
    for entry in config.pin.paths:
        try:
            base = ensure_within_root(root, root / entry, must_exist=True)
        except MakefileMcpError as exc:
            raise ConfigurationError(f"invalid pin path {entry!r}: {exc}") from exc
        paths.append(base)
        if base.is_dir():
            # Directories are listed too, so added, removed, or renamed files are noticed.
            for directory, subdirs, names in os.walk(base, followlinks=False):
                subdirs.sort()
                paths += [Path(directory, name) for name in (*subdirs, *names)]
    return tuple(sorted(set(paths), key=str))
