"""Read-only diagnostics for Make, contexts, exposure, and capabilities."""

import shutil
from pathlib import Path

from make_mcp.core.catalog import Catalog, Contexts
from make_mcp.models import (
    DoctorFinding,
    DoctorResult,
    DoctorSeverity,
    MakeMcpConfig,
    TaskRisk,
)


def run_doctor(
    *,
    root: Path,
    config: MakeMcpConfig,
    contexts: Contexts,
    catalog: Catalog,
) -> DoctorResult:
    findings: list[DoctorFinding] = []
    if shutil.which("make") is None:
        findings.append(
            DoctorFinding(
                code="make.unavailable",
                severity=DoctorSeverity.ERROR,
                message="GNU Make is not available on PATH",
            )
        )
    if not root.is_dir():
        findings.append(
            DoctorFinding(
                code="root.invalid",
                severity=DoctorSeverity.ERROR,
                message=f"repository root is not a directory: {root}",
            )
        )
        return DoctorResult(ok=False, findings=findings)

    discovered_anywhere: set[str] = set()
    exposed_anywhere: set[str] = set()
    for context_name in contexts.names():
        try:
            context = contexts.resolve(context_name)
            if not (context.directory / "Makefile").is_file():
                findings.append(
                    DoctorFinding(
                        code="context.makefile_missing",
                        severity=DoctorSeverity.ERROR,
                        message="context has no Makefile",
                        context=context_name,
                    )
                )
                continue
            snapshot = catalog.snapshot(context_name)
        except Exception as exc:  # doctor intentionally aggregates independent failures
            findings.append(
                DoctorFinding(
                    code="context.invalid",
                    severity=DoctorSeverity.ERROR,
                    message=str(exc),
                    context=context_name,
                )
            )
            continue

        discovered_anywhere.update(snapshot.discovered_targets)
        exposed_anywhere.update(snapshot.tasks)
        findings.extend(
            DoctorFinding(
                code="make.warning",
                severity=DoctorSeverity.WARNING,
                message=warning,
                context=context_name,
            )
            for warning in snapshot.warnings
        )
        findings.extend(
            DoctorFinding(
                code="task.dangerous_public",
                severity=DoctorSeverity.WARNING,
                message="dangerous task is publicly exposed",
                context=context_name,
                task=task.name,
            )
            for task in snapshot.tasks.values()
            if task.risk == TaskRisk.DANGEROUS
        )

    for name, task_config in sorted(config.tasks.items()):
        if task_config.enabled and name not in discovered_anywhere:
            findings.append(
                DoctorFinding(
                    code="task.missing",
                    severity=DoctorSeverity.ERROR,
                    message="configured exposed task was not discovered in any context",
                    task=name,
                )
            )

    for capability, target in sorted(config.capabilities.items()):
        if target not in exposed_anywhere:
            findings.append(
                DoctorFinding(
                    code="capability.invalid",
                    severity=DoctorSeverity.ERROR,
                    message=(
                        f"capability {capability!r} maps to target {target!r}, "
                        "which is not exposed in any context"
                    ),
                )
            )

    return DoctorResult(
        ok=not any(finding.severity == DoctorSeverity.ERROR for finding in findings),
        findings=findings,
    )
