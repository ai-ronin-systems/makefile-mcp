"""Conservative static Makefile discovery without evaluating GNU Make."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from make_mcp.errors import MakeInspectionError

# Recognize ordinary and double-colon rules while rejecting := / ::= variable assignments.
_TARGET_LINE = re.compile(r"^([^#\t ][^:=]*?)(?:::(?![=])|:(?![:=]))(.*)$")
_INCLUDE = re.compile(r"^(?P<directive>-?include|sinclude)\s+(?P<expression>.+)$")
_VALID_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@/+:-]*$")
_LITERAL_INCLUDE = re.compile(r"^[A-Za-z0-9._/@:+/-]+$")
_DEFINE_START = re.compile(r"^(?:(?:override|export|private)\s+)*define(?:\s|$)")
_DEFINE_END = re.compile(r"^endef(?:\s|$)")
_CONDITIONAL_START = re.compile(r"^(?:ifeq|ifneq|ifdef|ifndef)(?:\s|\()")
_CONDITIONAL_END = re.compile(r"^endif(?:\s|$)")
_VARIABLE_ASSIGNMENT = re.compile(
    r"^(?:(?:override|export|private|unexport)\s+)*[^\s:=]+\s*(?:\:\:\:=|\:\:=|\:=|\+=|\?=|!=|=)"
)
_TARGET_SPECIFIC_ASSIGNMENT = re.compile(
    r"^\s*(?:(?:override|export|private)\s+)*[^\s:=]+\s*(?:\:\:\:=|\:\:=|\:=|\+=|\?=|!=|=)"
)
_RECIPEPREFIX_ASSIGNMENT = re.compile(
    r"^(?:(?:override|export|private)\s+)*\.RECIPEPREFIX\s*(?::=|::=|\+=|\?=|!=|=)"
)
# These GNU Make directives may legitimately contain ':' in their arguments. They are not
# rule declarations, so generic target recognition must never infer callable names from them.
# Modifier-prefixed forms are skipped conservatively for the same reason.
_NON_RULE_DIRECTIVE = re.compile(
    r"^(?:override|private|vpath|export|unexport|undefine|load)(?:\s|$)"
)


@dataclass
class RawMakeTarget:
    """One statically discovered target before exposure policy is applied."""

    name: str
    description: str | None = None


@dataclass
class RawMakeCatalog:
    """Static discovery result including cache dependencies and conservative warnings."""

    targets: dict[str, RawMakeTarget] = field(default_factory=dict)
    # Missing optional literal includes are tracked too. Fingerprinting them lets the catalog
    # notice when a generated include later appears.
    tracked_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class _ParseState:
    """Mutable state shared while walking the literal Make include graph."""

    targets: dict[str, RawMakeTarget] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    tracked_files: list[str] = field(default_factory=list)
    phony_names: set[str] = field(default_factory=set)
    pending: list[Path] = field(default_factory=list)
    seen: set[Path] = field(default_factory=set)


def _description(line: str) -> str | None:
    """Extract a conventional ``##`` target description from one Makefile line."""
    if "##" not in line:
        return None
    text = line.split("##", 1)[1].strip()
    return text or None


def _target_names(lhs: str) -> list[str]:
    """Return target names from a rule left-hand side that fit the supported subset."""
    return [
        name
        for name in lhs.split()
        if not name.startswith(".")
        and "%" not in name
        and "$" not in name
        and _VALID_TARGET.fullmatch(name)
    ]


def _literal_include_paths(expression: str, warnings: list[str]) -> list[str]:
    """Return include tokens whose resolution can be modeled exactly."""
    # GNU Make includes support expansion, wildcards, escaped whitespace and other behavior
    # this intentionally small inspector does not emulate. Guessing can create false-positive
    # target names, so unsupported forms are warnings and remain inside the trusted Make layer.
    # Unescaped `#` begins a Make comment. Escaped-comment filenames are outside the literal
    # subset anyway because backslashes are not accepted by `_LITERAL_INCLUDE`.
    expression = expression.split("#", 1)[0].rstrip()
    tokens = expression.split()
    if not tokens or any(not _LITERAL_INCLUDE.fullmatch(token) for token in tokens):
        warnings.append(f"dynamic/unsupported include not tracked: {expression}")
        return []
    return tokens


def _is_recipeprefix_change(line: str) -> bool:
    """Return whether a line actually assigns GNU Make's custom recipe-prefix variable."""
    return bool(_RECIPEPREFIX_ASSIGNMENT.match(line))


def _queue_include(
    token: str,
    *,
    required: bool,
    invocation_directory: Path,
    repository_root: Path,
    state: _ParseState,
) -> None:
    """Resolve and queue one literal include using GNU Make invocation-directory semantics."""
    lexical = invocation_directory / token
    # Track the lexical path as well as the eventual resolved target so symlink retargeting
    # invalidates the cache even if the old target file itself did not change.
    state.tracked_files.append(str(lexical.absolute()))
    try:
        child = lexical.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise MakeInspectionError(f"could not resolve included Makefile {lexical}: {exc}") from exc
    try:
        child.relative_to(repository_root)
    except ValueError:
        state.warnings.append(f"ignored included Makefile outside repository: {child}")
        return

    if not lexical.exists():
        if required:
            raise MakeInspectionError(f"required included Makefile does not exist: {lexical}")
        state.warnings.append(f"optional included Makefile does not exist: {lexical}")
        return
    state.pending.append(child)


def _record_rule(line: str, state: _ParseState) -> None:
    """Record supported target declarations from one non-recipe Makefile line."""
    # Strip ordinary Make comments before generic rule recognition. Keep the original line for
    # conventional `##` description extraction below. Escaped-comment syntax is outside the
    # supported static subset, so a conservative false negative is preferable to guessing.
    code = line.split("#", 1)[0].rstrip()
    if not code:
        return

    if code.startswith(".PHONY:"):
        # GNU Make permits an inline recipe after `;`. Only the prerequisite portion names
        # phony targets; recipe text must never become callable discovery output. Escaped or
        # otherwise ambiguous semicolon forms are intentionally outside the static subset.
        phony_body = code.split(":", 1)[1].split(";", 1)[0]
        state.phony_names.update(phony_body.split())
        return

    if _VARIABLE_ASSIGNMENT.match(code):
        return

    if _NON_RULE_DIRECTIVE.match(code.lstrip()):
        return

    match = _TARGET_LINE.match(code)
    if not match:
        return

    lhs = match.group(1)
    # A Make expansion on the left-hand side can itself contain `:`. Filtering only the token
    # containing `$` can leave other expansion text behind as a phantom target, e.g.
    # `$(info note: hello)`. Reject the whole ambiguous line instead.
    if "$" in lhs:
        return

    # Target-/pattern-specific variable assignments do not themselves define a runnable rule.
    # Skipping an ambiguous prerequisite containing `=` is an acceptable false negative.
    if _TARGET_SPECIFIC_ASSIGNMENT.match(match.group(2)):
        return
    for name in _target_names(lhs):
        description = _description(line)
        existing = state.targets.get(name)
        if existing is None:
            state.targets[name] = RawMakeTarget(name=name, description=description)
        elif description and not existing.description:
            existing.description = description


def _parse_source_file(
    current: Path,
    *,
    invocation_directory: Path,
    repository_root: Path,
    state: _ParseState,
) -> None:
    """Inspect one literal Make source file using the intentionally small static subset."""
    define_depth = 0
    conditional_depth = 0
    physical_continuation = False
    try:
        lines = current.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise MakeInspectionError(f"could not inspect Makefile {current}: {exc}") from exc

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip()
        stripped = line.strip()
        if physical_continuation:
            # GNU Make joins backslash-newline continuations before parsing ordinary syntax, and
            # recipe continuations likewise do not require a tab on the next physical line. Skip
            # every continuation line so target-looking data cannot become a false positive.
            physical_continuation = raw_line.endswith("\\")
            continue
        physical_continuation = raw_line.endswith("\\")

        if not line or line.lstrip().startswith("#"):
            continue

        # Standard recipes begin with a tab. Ignore them before directive handling so recipe
        # text containing words such as `define` or `.RECIPEPREFIX` cannot affect discovery.
        if line.startswith("\t"):
            continue

        # `define` bodies are variable data and may contain target-looking text/directives.
        if define_depth:
            if _DEFINE_START.match(stripped):
                define_depth += 1
            elif _DEFINE_END.match(stripped):
                define_depth -= 1
            continue
        if _DEFINE_START.match(stripped):
            define_depth = 1
            state.warnings.append(f"define block not statically inspected: {current}:{line_number}")
            continue

        # Custom recipe prefixes invalidate the parser's core recipe/target distinction. Fail
        # closed instead of implementing another slice of GNU Make syntax.
        if _is_recipeprefix_change(stripped):
            raise MakeInspectionError(
                f"custom .RECIPEPREFIX is unsupported by static discovery: {current}:{line_number}"
            )

        # V1 does not evaluate Make conditionals. Skipping the whole block creates acceptable
        # false negatives rather than unsafe target names from branches GNU Make may not use.
        if conditional_depth:
            if _CONDITIONAL_START.match(stripped):
                conditional_depth += 1
            elif _CONDITIONAL_END.match(stripped):
                conditional_depth -= 1
            continue
        if _CONDITIONAL_START.match(stripped):
            conditional_depth = 1
            state.warnings.append(
                f"conditional Make block not statically inspected: {current}:{line_number}"
            )
            continue

        include = _INCLUDE.match(stripped)
        if include:
            directive = include.group("directive")
            required = directive == "include"
            for token in _literal_include_paths(include.group("expression"), state.warnings):
                _queue_include(
                    token,
                    required=required,
                    invocation_directory=invocation_directory,
                    repository_root=repository_root,
                    state=state,
                )
            continue

        _record_rule(line, state)

    if define_depth:
        raise MakeInspectionError(f"unterminated define block: {current}")
    if conditional_depth:
        raise MakeInspectionError(f"unterminated conditional block: {current}")


def parse_makefiles(makefile: Path, *, repository_root: Path) -> RawMakeCatalog:
    """Discover callable-looking target names from one conventional Makefile graph.

    Args:
        makefile: Exact top-level Makefile later pinned with ``make -f``.
        repository_root: Trusted root used to confine literal include traversal.

    Returns:
        Discovered target names, literal files to fingerprint, and conservative warnings.

    Raises:
        MakeInspectionError: If syntax invalidates safe discovery or a required literal include
            is unavailable.
    """
    try:
        makefile = makefile.resolve(strict=True)
        repository_root = repository_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise MakeInspectionError(f"could not resolve Makefile discovery paths: {exc}") from exc

    # GNU Make resolves relative include names from its invocation working directory, not the
    # containing include file. Execution uses cwd=<context>, so this fixed base must match it.
    invocation_directory = makefile.parent
    state = _ParseState(pending=[makefile])

    while state.pending:
        current = state.pending.pop()
        if current in state.seen:
            continue
        state.seen.add(current)
        try:
            current.relative_to(repository_root)
        except ValueError:
            state.warnings.append(f"ignored included Makefile outside repository: {current}")
            continue

        state.tracked_files.append(str(current))
        if not current.exists():
            # Only optional missing includes should reach this point; required missing includes
            # fail in `_queue_include` before being queued.
            state.warnings.append(f"optional included Makefile does not exist: {current}")
            continue

        _parse_source_file(
            current,
            invocation_directory=invocation_directory,
            repository_root=repository_root,
            state=state,
        )

    # A .PHONY declaration itself defines the named target for discovery. There is no retained
    # `phony` property because authorization/execution behavior does not depend on it.
    for name in state.phony_names:
        if name not in state.targets and _VALID_TARGET.fullmatch(name):
            state.targets[name] = RawMakeTarget(name=name)

    return RawMakeCatalog(
        targets=state.targets,
        tracked_files=state.tracked_files,
        warnings=state.warnings,
    )


class StaticMakeInspector:
    """Inspect the conventional context Makefile used by discovery and execution."""

    def __init__(self, repository_root: Path):
        """Create an inspector confined to *repository_root*."""
        self._repository_root = repository_root.resolve()

    def discover(self, *, directory: Path) -> RawMakeCatalog:
        """Inspect ``<directory>/Makefile`` and return the conservative static catalog."""
        # There is intentionally no arbitrary Makefile override: policy is tied to the
        # conventional context Makefile, and execution pins that same top-level file with -f.
        candidate = directory / "Makefile"
        try:
            if not candidate.is_file():
                raise MakeInspectionError(f"Makefile not found: {candidate}")
            return parse_makefiles(candidate, repository_root=self._repository_root)
        except OSError as exc:
            raise MakeInspectionError(f"could not inspect Makefile {candidate}: {exc}") from exc
