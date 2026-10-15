# Releasing

Releases are built once from a Git tag, gated on the full CI workflow, attested, published to PyPI through OIDC Trusted Publishing, listed in the MCP Registry, and attached to a GitHub Release. No long-lived PyPI or registry token exists anywhere.

The release workflow is `.github/workflows/release.yml`; MCP Registry publication is the reusable `.github/workflows/registry.yml`.

## Publishing credentials

Every publishing credential is a short-lived GitHub OIDC token minted inside the job that needs it:

| Destination | Mechanism | Repository-side setup |
| --- | --- | --- |
| PyPI | Trusted Publishing | publisher for `ai-ronin-systems/makefile-mcp`, workflow `release.yml`, environment `pypi` (configured) |
| MCP Registry | `mcp-publisher login github-oidc` | none; the `io.github.ai-ronin-systems/*` namespace follows from the repository owner |
| GitHub Release | workflow `GITHUB_TOKEN` | none |

If `release.yml` is renamed or the `pypi` environment changes, update the PyPI Trusted Publisher to match or PyPI publication fails closed.

The `pypi` GitHub environment has no protection rules by default. Adding a required reviewer there makes every PyPI publication wait for a human click.

Only `attest`, `publish-pypi`, and the registry job can mint OIDC tokens. None of them runs project code or restores a cache; architecture tests in `tests/unit/test_architecture.py` pin this. The default workflow permission is read-only.

## Dependency and workflow pinning

Release reproducibility and dependency hygiene have additional guardrails:

- the isolated PEP 517 build backend is exact-pinned in `pyproject.toml` (`hatchling==1.31.0`); update that pin intentionally rather than allowing an arbitrary future backend to build an old tag;
- the `setup-uv` Action is SHA-pinned and installs an explicit uv version (`0.12.1`) rather than whatever uv release happens to be latest;
- third-party GitHub Actions are referenced by immutable commit SHA with the corresponding release tag kept as a comment. `.github/dependabot.yml` maintains both GitHub Actions and the uv-locked Python dependency graph through reviewable pull requests;
- `make typecheck` runs exact-pinned Pyright as a separate CI/release gate without adding its Node-oriented wrapper to Makefile MCP's runtime or locked development dependency graph;
- the MCP Registry publisher (`mcp-publisher`) is downloaded at an exact version and verified against a pinned SHA-256 before it runs;
- `make dependency-audit` exports the frozen runtime dependency set and checks it with exact-pinned `pip-audit`. This gate intentionally uses live package/advisory services and therefore stays separate from deterministic `make check`.

A release dependency update should pass the same `make check`, static type gate, dependency audit, package build, clean-container smoke test, and release-identity checks as any other release change.

## Release contract

A public release tag must use exactly `vX.Y.Z` and match the single package version in `src/makefile_mcp/version.py`. `scripts/check_release.py` also requires:

1. the tagged commit to be reachable from `main` (checked in the workflow);
2. an empty `## Unreleased` section in `CHANGELOG.md`;
3. a dated `## X.Y.Z — YYYY-MM-DD` changelog section;
4. `server.json` and the README MCP Registry ownership marker matching the same version and registry name;
5. exactly one wheel and one `.tar.gz` source distribution after build, whose embedded `Name` and `Version` metadata match the repository.

## Cutting a release

On an up-to-date, clean `main`:

```bash
# 1. Bump the version in both places, and date the CHANGELOG section.
$EDITOR src/makefile_mcp/version.py server.json CHANGELOG.md

# 2. Run the full local release gate (check, typecheck, audit, identity, build, smoke, Docker).
make prepublish TAG=vX.Y.Z

# 3. Commit, push, and wait for CI to pass on main.
git commit -am "Release X.Y.Z" && git push origin main

# 4. Tag the release commit and push the tag.
git tag -a vX.Y.Z -m "Makefile MCP X.Y.Z"
git push origin vX.Y.Z
```

The tag push triggers the release workflow. Do not upload a separate local build to PyPI; the workflow publishes the exact artifacts that passed release validation.

## Automated release flow

```text
annotated Git tag vX.Y.Z
          |
          v
release workflow
  |
  +-- ci: the full CI workflow (Linux/macOS x Python matrix, Pyright,
  |       dependency audit, package smoke) runs on the tagged commit
  |
  +-- build (read-only, no dependency cache)
  |     +-- tag commit is reachable from main
  |     +-- tag == version == changelog == server.json
  |     +-- build wheel + sdist once
  |     +-- inspect embedded package metadata
  |     `-- clean-container wheel + stdio MCP smoke test
  |
  +-- attest (OIDC; runs no project code)
  |     `-- GitHub build provenance attestation
  |
  +-- same artifacts -> PyPI via OIDC
  |     |
  |     `-- server.json -> MCP Registry via OIDC
  |
  `-- same artifacts -> GitHub Release
```

Nothing publishes unless the full CI gate passes on the exact tagged commit, so a compromised test dependency or poisoned cache cannot sign or publish artifacts.

## Clean-container smoke test

`make package-smoke` mounts `dist/` read-only into a stock Python container, installs the wheel rather than the working tree, installs GNU Make, verifies both the CLI and the installed stdio MCP server, then installs the sdist in a fresh virtual environment to prove that both published artifact formats are installable:

```text
makefile-mcp --version
makefile-mcp doctor
makefile-mcp list
makefile-mcp run test
MCP stdio handshake
MCP list_tools
MCP run_task(test)
```

This catches missing package files, broken console-script metadata, undeclared runtime dependencies, source-tree-only imports, wheel/sdist packaging defects, and entry-point defects that only appear when an MCP client launches the installed server over real stdio.

## MCP Registry

The registry name is `io.github.ai-ronin-systems/makefile-mcp`. `server.json` declares the PyPI package and its `serve` argument, and the README carries the hidden `mcp-name` ownership marker the registry checks on PyPI. The registry job runs only after PyPI publication, because ownership validation needs the package to exist.

The job verifies that `server.json` matches the tag, installs the pinned publisher, logs in with GitHub OIDC, and publishes. To list a version that is already on PyPI (for example after a failed registry step), run **Actions → MCP Registry → Run workflow** and pick that release tag; the job refuses to run on branches.

Check `server.json` locally with `mcp-publisher validate`.

## After a release is public

PyPI files and descriptions are immutable, and public tags should be treated the same way. Any fix, including a README-only one, ships as the next patch version:

```text
fix -> version X.Y.(Z+1) -> changelog -> tag vX.Y.(Z+1)
```

If validation or build fails before anything reaches PyPI, fix the source commit, delete the unpublished tag (`git push origin :vX.Y.Z`), and tag again.

If PyPI publication succeeds but the registry or GitHub Release job fails, do not rebuild or republish the Python package. Re-run only the failed job, or for the registry use the manual dispatch above.

## Public repository metadata

GitHub's About panel and repository topics are not stored in the source tree. Keep them set explicitly:

**Description**

```text
Expose trusted GNU Make targets as typed, governed MCP tools — without a generic shell or second workflow DSL.
```

**Topics**

```text
mcp
model-context-protocol
gnu-make
makefile
ai-agents
developer-tools
python
automation
security
```

Use the PyPI project or repository documentation URL as the website link.
