"""Small composition root and protocol-agnostic application facade."""

from dataclasses import dataclass
from pathlib import Path

from make_mcp.config import load_config
from make_mcp.core.catalog import Catalog, Contexts
from make_mcp.core.doctor import run_doctor
from make_mcp.core.execution import TaskExecutor
from make_mcp.infrastructure.filesystem import FileContextLock, detect_repository_root
from make_mcp.infrastructure.make import StaticMakeInspector
from make_mcp.infrastructure.process import SubprocessRunner
from make_mcp.models import DoctorResult, MakeMcpConfig, TaskDefinition, TaskResult


@dataclass(frozen=True)
class Application:
    root: Path
    config: MakeMcpConfig
    contexts: Contexts
    catalog: Catalog
    executor: TaskExecutor

    def list_tasks(self, context: str = "root") -> list[TaskDefinition]:
        return self.catalog.list(context)

    def describe_task(self, task: str, context: str = "root") -> TaskDefinition:
        return self.catalog.describe(task, context)

    def resolve_capability(self, capability: str, context: str = "root") -> TaskDefinition:
        return self.catalog.resolve_capability(capability, context)

    async def run_task(
        self,
        task: str,
        variables: dict[str, str] | None = None,
        context: str = "root",
    ) -> TaskResult:
        return await self.executor.run(task, variables, context)

    def doctor(self) -> DoctorResult:
        return run_doctor(
            root=self.root,
            config=self.config,
            contexts=self.contexts,
            catalog=self.catalog,
        )


def build_application(start: Path | None = None) -> Application:
    root = detect_repository_root(start or Path.cwd())
    config = load_config(root)
    contexts = Contexts(root, config)
    catalog = Catalog(
        root=root,
        config=config,
        contexts=contexts,
        inspector=StaticMakeInspector(root),
    )
    executor = TaskExecutor(
        root=root,
        config=config,
        contexts=contexts,
        catalog=catalog,
        runner=SubprocessRunner(),
        lock=FileContextLock(root),
    )
    return Application(
        root=root,
        config=config,
        contexts=contexts,
        catalog=catalog,
        executor=executor,
    )
