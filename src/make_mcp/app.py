"""Small composition root and protocol-agnostic application facade."""

from dataclasses import dataclass
from pathlib import Path

from make_mcp.catalog import Catalog, Contexts
from make_mcp.config import load_config_state
from make_mcp.doctor import run_doctor
from make_mcp.errors import ConfigurationError
from make_mcp.execution import TaskExecutor
from make_mcp.filesystem import Fingerprint, FileContextLock, detect_repository_root, fingerprint
from make_mcp.makefile import StaticMakeInspector
from make_mcp.models import DoctorResult, MakeMcpConfig, TaskDefinition, TaskResult
from make_mcp.process import SubprocessRunner


@dataclass(frozen=True)
class Application:
    """Protocol-independent facade over catalog, diagnostics, and task execution."""

    root: Path
    config: MakeMcpConfig
    contexts: Contexts
    catalog: Catalog
    executor: TaskExecutor
    governed: bool
    policy_fingerprint: Fingerprint

    def _ensure_policy_current(self) -> None:
        """Fail closed if the authorization policy changed since application startup."""
        try:
            current = fingerprint([self.root / ".make-mcp.yaml"])
        except (OSError, RuntimeError) as exc:
            raise ConfigurationError(f"could not verify .make-mcp.yaml state: {exc}") from exc
        if current != self.policy_fingerprint:
            raise ConfigurationError(
                ".make-mcp.yaml changed since startup; restart make-mcp to apply policy safely"
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
    ) -> TaskResult:
        """Execute or preview one callable task through the shared bounded executor."""
        self._ensure_policy_current()
        return await self.executor.run(task, variables, context, preview=preview)

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


def build_application(start: Path | None = None) -> Application:
    """Compose one application instance rooted at *start* or the current directory."""
    root = detect_repository_root(start or Path.cwd())
    loaded = load_config_state(root)
    contexts = Contexts(root, loaded.config)
    catalog = Catalog(
        config=loaded.config,
        contexts=contexts,
        inspector=StaticMakeInspector(root),
        governed=loaded.governed,
    )
    executor = TaskExecutor(
        root=root,
        config=loaded.config,
        contexts=contexts,
        catalog=catalog,
        runner=SubprocessRunner(),
        lock=FileContextLock(root),
    )
    return Application(
        root=root,
        config=loaded.config,
        contexts=contexts,
        catalog=catalog,
        executor=executor,
        governed=loaded.governed,
        policy_fingerprint=loaded.policy_fingerprint,
    )
