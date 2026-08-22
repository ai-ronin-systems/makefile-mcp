# Deployment

The built-in MCP transport in Just Make It MCP (JMIM) is **stdio**. A deployment is therefore a process (local or containerized) launched by an MCP client or orchestrator with the target repository available as its working tree.

When a container helper launches the stdio server, do not allocate a pseudo-TTY. The provided `make docker-serve` uses `docker compose run -T` so JSON-RPC stdio remains a raw byte stream.

For repeatable environments, prefer an immutable container image that contains:

1. JMIM;
2. every command-line tool used by callable recipes;
3. the intended `Makefile` and optional `.make-mcp.yaml` (or a mounted trusted repository);
4. any trusted wrapper scripts required by those recipes.

Make remains the only execution definition.

## Build the base image

From the JMIM repository:

```bash
make docker-build
```

or:

```bash
docker build -t make-mcp:<version> .
```

The base image contains Python, GNU Make, CA certificates, and JMIM. It intentionally does **not** try to install every third-party tool a repository might call.

The repository release workflow is more reproducible than this convenience base image: the Dockerfile currently uses a mutable Python slim tag and distribution packages. Treat a deployed image digest as the immutable artifact, and pin the base image/tool packages in a derived production image when byte-for-byte rebuild reproducibility matters. Do not infer image reproducibility from the Python lockfile alone.

## Development/brownfield: mount an existing repository

For a repository whose required tools already exist in the image:

```bash
docker run --rm --init -i \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  -w /workspace \
  make-mcp:<version> serve --tools direct
```

Use `--tools generic` for an orchestrator-oriented stable API.

Mount only trusted repository content. The Makefile is executable trusted code, not untrusted data.

## Recommended production pattern: custom runtime image

Provision recipe dependencies in a derived image instead of teaching JMIM about scanners, build systems, package managers, or other execution providers.

Example project:

```text
mcp-runtime/
├── Dockerfile
├── Makefile
├── .make-mcp.yaml
└── scripts/
    └── collect.py
```

Example derived image:

```dockerfile
FROM make-mcp:<version>

USER root

# Install only the tools required by the trusted Makefile.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git jq curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 make-mcp

WORKDIR /workspace
COPY --chown=make-mcp:make-mcp Makefile .make-mcp.yaml ./
COPY --chown=make-mcp:make-mcp scripts ./scripts

USER make-mcp
ENTRYPOINT ["make-mcp"]
CMD ["serve", "--tools", "generic"]
```

Build and validate:

```bash
docker build -t my-make-mcp-runtime:1 .
docker run --rm my-make-mcp-runtime:1 doctor
docker run --rm my-make-mcp-runtime:1 list
```

Run it as an MCP stdio process:

```bash
docker run --rm --init -i my-make-mcp-runtime:1 serve --tools generic
```

This is the preferred model for evidence providers and other controlled automation services: the image version determines JMIM, tool versions, Makefile policy, and wrapper code together.

## Provisioning non-APT tools

Keep provisioning explicit in the Dockerfile. Common patterns are:

- install from the distribution package manager;
- copy a pinned binary from a dedicated builder stage;
- install a pinned Python/Node/Java tool in the image;
- copy an internally built binary/artifact into the runtime stage.

Example multi-stage pattern:

```dockerfile
FROM vendor/tool-image:1.2.3 AS tool

FROM make-mcp:<version>
COPY --from=tool /usr/local/bin/example-tool /usr/local/bin/example-tool

RUN useradd --create-home --uid 10001 make-mcp
WORKDIR /workspace
COPY --chown=make-mcp:make-mcp Makefile .make-mcp.yaml ./
USER make-mcp
ENTRYPOINT ["make-mcp"]
CMD ["serve", "--tools", "generic"]
```

Pin versions. Avoid `curl | sh`, floating `latest` tags, or runtime package installation in production images when reproducibility matters.

## Keep tool integration in Make

The container provisions binaries; the Makefile defines how they run:

```make
.PHONY: scan report

scan: ## Run the provisioned scanner
	example-tool scan --output report.json .

report: scan ## Normalize scanner output
	python3 scripts/collect.py report.json
```

Govern only the callable surface:

```yaml
schema_version: 1

tasks:
  scan:
    risk: write
  report:
    risk: safe

capabilities:
  appsec_scan: scan
```

Do not add tool-specific executors to JMIM merely because a Docker image contains those tools.

## Repository-mounted vs image-baked policy

### Mount the repository

Use when development velocity matters and the host repository is the source of truth.

```text
image: JMIM + toolchain
mount: Makefile + config + source
```

Changing `.make-mcp.yaml` still requires restarting the JMIM process.

### Bake the repository contract

Use when reproducibility and deployment review matter more than live edits.

```text
image: JMIM + toolchain + Makefile + .make-mcp.yaml + wrappers
```

This gives one immutable artifact for the callable contract and its runtime dependencies.

## User and filesystem permissions

The base development Compose setup maps the host UID/GID. For production, run with the least filesystem permissions the recipes need.

Writable directories should be explicit. Do not grant broad host mounts, Docker socket access, privileged mode, or host networking unless a trusted recipe genuinely requires them; those privileges sit outside JMIM's security boundary.

When JMIM is PID 1 in a container, use an init process (`docker run --init` or Compose `init: true`) so orphaned recipe descendants are reaped correctly. JMIM manages the task process group but is not a general-purpose process supervisor.

Lock files are created under:

```text
.make-mcp/locks/
```

so the repository/runtime user needs write permission there.

## Secrets and environment

Inject secrets through the deployment mechanism, then explicitly inherit only the names required by governed configuration:

```yaml
environment:
  inherit:
    - PATH
    - HOME
    - USER
    - API_TOKEN
```

Setting `inherit` replaces JMIM's default `[PATH, HOME, USER]` list; it does not append to it. Keep the defaults explicitly when they are still required by recipes. `environment.allow` overrides inherited values with trusted configured literals.

Do not bake secrets into the image, Makefile, or `.make-mcp.yaml`. Scalar governed task inputs are also not a secret channel because they cross GNU Make as command-line assignments; use the deployment environment/secret mechanism for secrets.

Remember that trusted recipes can read inherited environment variables. See [Security](security.md#make-variables-and-process-environments).

## Validation before deployment

At minimum:

```bash
make-mcp doctor
make-mcp list
```

For a derived image:

```bash
docker run --rm my-make-mcp-runtime:1 doctor
docker run --rm my-make-mcp-runtime:1 list
```

For the JMIM project itself:

```bash
make docker-check
```

## Production checklist

Before exposing a repository to an agent or orchestrator:

- [ ] repository Makefiles, included Make code, wrapper scripts, and provisioned tools are trusted;
- [ ] `.make-mcp.yaml` is present for non-trivial or shared agent use;
- [ ] `make-mcp doctor` exits cleanly;
- [ ] callable task inventory and dangerous-risk declarations have been reviewed;
- [ ] only required environment names are inherited or injected;
- [ ] the runtime user has only the filesystem permissions recipes require;
- [ ] `.make-mcp/locks` is writable by the runtime user;
- [ ] container execution uses an init process;
- [ ] MCP stdio is run without a pseudo-TTY;
- [ ] Docker socket, privileged mode, host networking, and broad host mounts are absent unless explicitly required;
- [ ] production image/tool versions or the deployed image digest are recorded.

## Network exposure

JMIM does not expose an HTTP listener. The supported server runs over stdio. If another system wraps it in a network service, that wrapper owns authentication, authorization to reach the process, TLS, rate limiting, and network isolation.

Do not infer network safety from JMIM's local stdio threat model.
