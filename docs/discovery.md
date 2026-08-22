# Static Make discovery

JMIM builds its callable inventory with a deliberately conservative **static** inspector. Discovery answers one security-sensitive question:

> Which target names can JMIM safely recognize without evaluating GNU Make semantics?

It is not a complete GNU Make parser, and it is not a Makefile validator. The design rule is:

> **Prefer a false negative over accidentally authorizing target-looking text.**

## Why JMIM does not use `make -qp`

Asking GNU Make to load and print its internal rule database would provide richer semantic information, but loading/evaluating Makefiles can itself perform Make semantics: functions can execute commands, included files can be remade, and dynamic content can affect the evaluated graph.

JMIM therefore does not execute GNU Make merely to enumerate MCP tools. Discovery trades completeness for a non-evaluating authorization inventory. GNU Make remains authoritative only when an already-authorized task is actually invoked.

## Canonical file

Each context inspects the conventional:

```text
<context-directory>/Makefile
```

Execution later pins the same top-level file with `make -f`. GNU Make may still load dynamic or external includes at execution time; those files are trusted execution code but may be outside JMIM's discoverable static inventory.

## Supported rule forms

The inspector recognizes conservative ordinary forms such as:

```make
test:

test: dependency

test::

.PHONY: test

test: ## Run tests
```

Normal inline comments are removed before generic rule recognition while `##` descriptions on actual targets are retained as presentation metadata.

## Literal includes

Supported literal include directives use GNU Make's invocation-directory semantics:

```make
include common.mk
-include optional.mk
sinclude optional.mk
```

- a missing required literal `include` fails discovery;
- a missing optional `-include`/`sinclude` produces a warning;
- missing optional paths are fingerprinted so later creation refreshes the catalog;
- lexical and resolved paths are tracked so include symlink retargeting refreshes the catalog.

Dynamic, variable-expanded, globbed, escaped, or otherwise unsupported include expressions are not interpreted. External/out-of-repository includes may affect final GNU Make execution but their targets are not guaranteed to be discoverable by JMIM.

## Constructs skipped conservatively

Target-looking text is not inferred from constructs that are unsafe or ambiguous to classify statically, including:

```make
define NAME
...
endef

override define NAME
...
endef

ifeq (...)
...
endif

vpath %.c src:generated
export NAME
unexport NAME
undefine NAME
load plugin.so

$(info note: text)
$(warning note: text)
```

Rule-looking left-hand sides containing Make expansion (`$`) are ignored wholesale instead of being partially tokenized.

Recipe and variable continuations are tracked so continuation text cannot become phantom targets. Target-specific and colon-style variable assignments are likewise not treated as callable rules.

`.PHONY` processing accepts only the prerequisite portion before an inline recipe separator (`;`), preventing recipe tokens from becoming phantom tools that GNU Make could later satisfy through implicit rules.

## Fail-closed conditions

Discovery raises an error rather than guessing when it encounters conditions such as:

- an actual custom `.RECIPEPREFIX` assignment;
- an unterminated `define` block;
- an unterminated conditional block;
- a missing required literal include;
- unsafe filesystem resolution required to inspect a tracked file.

Some unsupported/dynamic constructs produce warnings instead of errors when they can be safely omitted from the callable inventory.

## False negatives are expected

A valid GNU Make target can be absent from JMIM's inventory when the target is generated or expressed through syntax the static inspector intentionally does not model. The recommended remediation is to provide a small, stable wrapper target with ordinary syntax:

```make
.PHONY: agent-verify
agent-verify: ## Stable JMIM entry point
	$(MAKE) complex-generated-target
```

This keeps the agent-facing authorization surface explicit while GNU Make continues to own the underlying workflow.

## Discovery versus execution trust

Static discovery and GNU Make execution have different scopes:

```text
static discovery
  -> conservative repository inventory

actual execution
  -> trusted GNU Make graph
  -> dynamic/generated/external includes may participate
```

JMIM does not sandbox trusted Makefiles or filesystem reads performed by GNU Make. See [Security](security.md) for the complete trust boundary.

## Cache lifecycle

Discovery snapshots are cached per context and fingerprint the top-level Makefile plus tracked literal include paths. Supported edits, inode/ctime/mtime changes, missing optional include creation, and include-symlink retargeting invalidate the snapshot.

`.make-mcp.yaml` is a separate startup authorization policy. It is never hot-reloaded; if its presence or contents change, subsequent operations fail closed until JMIM restarts.

Generic MCP/CLI catalog calls observe refreshed supported discovery state. Direct MCP tool registration is a startup snapshot, but an existing direct tool re-enters live authorization before execution.
