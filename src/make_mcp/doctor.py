"""Read-only diagnostics for Make, contexts, exposure, and capabilities."""

import os
import shutil
from pathlib import Path

from make_mcp.catalog import Catalog, Contexts
from make_mcp.errors import MakeMcpError
from make_mcp.models import DoctorFinding, DoctorResult, DoctorSeverity, MakeMcpConfig, TaskRisk


def _effective_path(config: MakeMcpConfig) -> str:
    """Return PATH as task execution will see it, including exec's default-path fallback."""
    if "PATH" in config.environment.allow:
        return config.environment.allow["PATH"]
    if "PATH" in config.environment.inherit and "PATH" in os.environ:
        return os.environ["PATH"]
    return os.defpath


def _runtime_findings(root: Path, config: MakeMcpConfig) -> list[DoctorFinding]:
    """Return host/runtime findings that do not require catalog traversal."""
    findings: list[DoctorFinding] = []
    if shutil.which("make", path=_effective_path(config)) is None:
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
    return findings


def _context_findings(
    contexts: Contexts,
    catalog: Catalog,
) -> tuple[list[DoctorFinding], dict[str, set[str]], set[str]]:
    """Inspect every context and return findings plus discovery/exposure indexes."""
    findings: list[DoctorFinding] = []
    discovered_by_context: dict[str, set[str]] = {}
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
        except (MakeMcpError, OSError) as exc:
            findings.append(
                DoctorFinding(
                    code="context.invalid",
                    severity=DoctorSeverity.ERROR,
                    message=str(exc),
                    context=context_name,
                )
            )
            continue

        discovered_by_context[context_name] = snapshot.discovered_targets
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

    return findings, discovered_by_context, exposed_anywhere


def _duplicate_context_findings(contexts: Contexts) -> list[DoctorFinding]:
    """Return errors when multiple names resolve to the same physical directory."""
    by_directory: dict[Path, list[str]] = {}
    for name in contexts.names():
        try:
            directory = contexts.resolve(name).directory.resolve()
        except (MakeMcpError, OSError):
            continue
        by_directory.setdefault(directory, []).append(name)

    return [
        DoctorFinding(
            code="context.duplicate_directory",
            severity=DoctorSeverity.ERROR,
            message=(
                "multiple context names resolve to the same physical directory: "
                + ", ".join(sorted(names))
            ),
        )
        for names in by_directory.values()
        if len(names) > 1
    ]


def _configured_task_findings(
    config: MakeMcpConfig,
    discovered_by_context: dict[str, set[str]],
) -> list[DoctorFinding]:
    """Return errors for configured tasks missing from conservative discovery."""
    findings: list[DoctorFinding] = []
    for name, task_config in sorted(config.tasks.items()):
        if not task_config.enabled:
            continue
        for context_name in task_config.contexts:
            if name not in discovered_by_context.get(context_name, set()):
                findings.append(
                    DoctorFinding(
                        code="task.missing",
                        severity=DoctorSeverity.ERROR,
                        message="configured exposed task was not discovered in this context",
                        context=context_name,
                        task=name,
                    )
                )
    return findings


def _capability_findings(
    config: MakeMcpConfig,
    exposed_anywhere: set[str],
) -> list[DoctorFinding]:
    """Return errors for capabilities that never resolve to an exposed target."""
    findings: list[DoctorFinding] = []
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
    return findings


def run_doctor(
    *,
    root: Path,
    config: MakeMcpConfig,
    contexts: Contexts,
    catalog: Catalog,
    governed: bool,
) -> DoctorResult:
    """Run all read-only diagnostics and return one normalized result."""
    findings = _runtime_findings(root, config)
    if not governed:
        findings.append(
            DoctorFinding(
                code="exposure.auto",
                severity=DoctorSeverity.WARNING,
                message=(
                    "auto mode exposes every conservatively discovered target; "
                    "use .make-mcp.yaml (governed mode) for explicit agent authorization"
                ),
            )
        )
    if any(finding.code == "root.invalid" for finding in findings):
        return DoctorResult(ok=False, findings=findings)

    context_findings, discovered_by_context, exposed_anywhere = _context_findings(
        contexts,
        catalog,
    )
    findings.extend(context_findings)
    findings.extend(_duplicate_context_findings(contexts))
    findings.extend(_configured_task_findings(config, discovered_by_context))
    findings.extend(_capability_findings(config, exposed_anywhere))

    return DoctorResult(
        ok=not any(finding.severity == DoctorSeverity.ERROR for finding in findings),
        findings=findings,
    )
