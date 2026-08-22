# Releasing

Just Make It MCP (JMIM) `0.1.0` is the project's first public release. There is no earlier public package lineage, migration path, or compatibility promise to preserve.

Releases are built once from a Git tag, validated, attested, published to PyPI through OIDC Trusted Publishing, and then attached to a GitHub Release. No long-lived PyPI API token is required.

The release workflow is `.github/workflows/release.yml`.

## First public release setup

### PyPI pending publisher

Because `make-mcp` is being published for the first time, configure a **pending GitHub Trusted Publisher** on PyPI. The first successful trusted publication creates the PyPI project.

Use:

| Field | Value |
| --- | --- |
| Owner | `ai-ronin-systems` |
| Repository | `make-mcp` |
| Workflow | `release.yml` |
| Environment | `pypi` |

No `PYPI_TOKEN` GitHub secret is used.

After `0.1.0` exists on PyPI, manage the publisher from the normal project publishing settings.

### GitHub environment

Create a GitHub Actions environment named `pypi`.

Protection rules are optional for the initial release. A required reviewer can be added later if publication becomes a multi-maintainer operation.

The workflow requests privileged permissions only in the jobs that need them:

- build: OIDC + attestations for provenance;
- PyPI: OIDC for Trusted Publishing;
- GitHub Release: repository contents write.

The default workflow permission remains read-only.

## Dependency and workflow pinning

Release reproducibility has two additional guardrails:

- the isolated PEP 517 build backend is exact-pinned in `pyproject.toml` (`hatchling==1.31.0`); update that pin intentionally rather than allowing an arbitrary future backend to build an old tag;
- the `setup-uv` Action is SHA-pinned and installs an explicit uv version (`0.12.1`) rather than whatever uv release happens to be latest;
- third-party GitHub Actions are referenced by immutable commit SHA with the corresponding release tag kept as a comment. `.github/dependabot.yml` maintains both GitHub Actions and the uv-locked Python dependency graph through reviewable pull requests.

A release dependency update should pass the same `make check`, package build, clean-container smoke test, and release-identity checks as any other release change.

## Release contract

A public release tag must use exactly:

```text
vX.Y.Z
```

and must match the single package version in:

```text
src/make_mcp/version.py
```

Before a tag can publish, `scripts/check_release.py` also requires:

1. an empty `## Unreleased` section in `CHANGELOG.md`;
2. a dated `## X.Y.Z — YYYY-MM-DD` changelog section;
3. exactly one wheel and one `.tar.gz` source distribution after build;
4. embedded distribution `Name` and `Version` metadata matching the repository.

For the first release, the expected identity is therefore:

```text
Git tag             v0.1.0
Package version     0.1.0
Changelog section   0.1.0
Distribution name   make-mcp
```

## Cutting 0.1.0

Prepare the intended public source tree on `main`:

```bash
# 1. Confirm the first public version.
grep __version__ src/make_mcp/version.py

# 2. Confirm CHANGELOG has an empty Unreleased section and one 0.1.0 release section.
#    Set that section date to the actual date this tag will be published.
$EDITOR CHANGELOG.md

# 3. Run normal release-blocking checks.
make check

# 4. Validate first-release identity locally.
make release-check TAG=v0.1.0

# 5. Build and validate distributions.
make package
make release-check-dist TAG=v0.1.0

# 6. Strongly recommended: install/run the built wheel in a clean container.
make package-smoke
```

Commit and push the prepared tree, then tag the intended `main` commit:

```bash
git switch main
git pull --ff-only
git status --short
git tag -a v0.1.0 -m "JMIM 0.1.0"
git push origin v0.1.0
```

The tag push triggers the release workflow. Do not upload a separate local build to PyPI; the workflow publishes the exact artifacts that passed release validation.

## Automated release flow

```text
annotated Git tag v0.1.0
          |
          v
release workflow
  |
  +-- make check
  +-- tag == version == changelog
  +-- build wheel + sdist once
  +-- inspect embedded package metadata
  +-- clean-container wheel smoke test
  +-- GitHub build provenance attestation
  |
  +-- same artifacts -> PyPI via OIDC
  |
  `-- same artifacts -> GitHub Release
```

PyPI Trusted Publishing uses GitHub's short-lived OIDC identity. The workflow intentionally contains no fallback username/password or long-lived API-token path.

## Clean-container smoke test

`make package-smoke` mounts `dist/` read-only into a stock Python container, installs the wheel rather than the working tree, installs GNU Make, and verifies:

```text
make-mcp --version
make-mcp doctor
make-mcp list
make-mcp run hello
```

This catches missing package files, broken console-script metadata, undeclared runtime dependencies, and source-tree-only imports.

## If the first release fails before publication

If validation or build fails before anything reaches PyPI, fix the source commit, remove the unpublished tag if necessary, rerun the checks, and create `v0.1.0` from the corrected commit.

There is no migration concern at this point because no public `make-mcp` package release exists yet.

## After 0.1.0 is public

Once a version has reached PyPI, its files are immutable and its tag should be treated as immutable as well. Fixes should use the next version rather than overwriting an existing public release.

For example, a post-publication fix to `0.1.0` becomes `0.1.1`:

```text
fix code -> version 0.1.1 -> changelog 0.1.1 -> tag v0.1.1
```

If PyPI publication succeeds but GitHub Release creation fails, do not rebuild or republish the Python package. Re-run only the failed GitHub Release job so it consumes the already validated workflow artifact.
