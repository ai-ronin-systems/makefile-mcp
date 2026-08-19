# Deployment

The built-in MCP transport in Makefile MCP is **stdio**. A deployment is therefore a process (local or containerized) launched by an MCP client or orchestrator with the target repository available as its working tree.

When a container helper launches the stdio server, do not allocate a pseudo-TTY. The provided `make docker-serve` uses `docker compose run -T` so JSON-RPC stdio remains a raw byte stream.

For repeatable environments, prefer an immutable container image that contains:

1. Makefile MCP;
2. every command-line tool used by callable recipes;
3. the intended `Makefile` and optional `.makefile-mcp.yaml` (or a mounted trusted repository);
4. any trusted wrapper scripts required by those recipes.

Make remains the only execution definition.

## Build the base image

From the Makefile MCP repository:

```bash
make docker-build
```

or:

```bash
docker build -t makefile-mcp:<version> .
```

The base image contains Python, GNU Make, CA certificates, and Makefile MCP. It runs as the dedicated non-root `makefile-mcp` user (UID/GID `10001`) by default and intentionally does **not** try to install every third-party tool a repository might call. For bind-mounted development repositories, override the container user to the host UID/GID as shown below so recipes can write normal workspace artifacts without root-owned files.

The repository release workflow is more reproducible than this convenience base image: the Dockerfile currently uses a mutable Python slim tag and distribution packages. Treat a deployed image digest as the immutable artifact, and pin the base image/tool packages in a derived production image when byte-for-byte rebuild reproducibility matters. Do not infer image reproducibility from the Python lockfile alone.

## Development/brownfield: mount an existing repository

For a repository whose required tools already exist in the image:

```bash
docker run --rm --init -i \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  -w /workspace \
  makefile-mcp:<version> serve --tools direct
```

Use `--tools generic` for an orchestrator-oriented stable API.

Mount only trusted repository content. The Makefile is executable trusted code, not untrusted data.

## Recommended production pattern: custom runtime image

Provision recipe dependencies in a derived image instead of teaching Makefile MCP about build systems, package managers, generators, or other project-specific tools.

Example project:

```text
mcp-runtime/
├── Dockerfile
├── Makefile
├── .makefile-mcp.yaml
└── scripts/
    └── package.py
```

Example derived image:

```dockerfile
FROM makefile-mcp:<version>

USER root

# Install only the tools required by the trusted Makefile.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git jq curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY --chown=makefile-mcp:makefile-mcp Makefile .makefile-mcp.yaml ./
COPY --chown=makefile-mcp:makefile-mcp scripts ./scripts

USER makefile-mcp
ENTRYPOINT ["makefile-mcp"]
CMD ["serve", "--tools", "generic"]
```

Build and validate:

```bash
docker build -t my-makefile-mcp-runtime:1 .
docker run --rm my-makefile-mcp-runtime:1 doctor
docker run --rm my-makefile-mcp-runtime:1 list
```

Run it as an MCP stdio process:

```bash
docker run --rm --init -i my-makefile-mcp-runtime:1 serve --tools generic
```

This is the preferred model for controlled automation services: the image version determines Makefile MCP, tool versions, Makefile policy, and wrapper code together.

## Provisioning non-APT tools

Keep provisioning explicit in the Dockerfile. Common patterns are:

- install from the distribution package manager;
- copy a pinned binary from a dedicated builder stage;
- install a pinned Python/Node/Java tool in the image;
- copy an internally built binary/artifact into the runtime stage.

Example multi-stage pattern:

```dockerfile
FROM vendor/tool-image:1.2.3 AS tool

FROM makefile-mcp:<version>
USER root
COPY --from=tool /usr/local/bin/example-tool /usr/local/bin/example-tool
WORKDIR /workspace
COPY --chown=makefile-mcp:makefile-mcp Makefile .makefile-mcp.yaml ./
USER makefile-mcp
ENTRYPOINT ["makefile-mcp"]
CMD ["serve", "--tools", "generic"]
```

Pin versions. Avoid `curl | sh`, floating `latest` tags, or runtime package installation in production images when reproducibility matters.

## Keep tool integration in Make

The container provisions binaries; the Makefile defines how they run:

```make
.PHONY: build package

build: ## Build with the provisioned project tool
	example-tool build --output dist .

package: build ## Produce the project package
	python3 scripts/package.py dist
```

Govern only the callable surface:

```yaml
schema_version: 1

tasks:
  build:
    risk: write
  package:
    risk: write

capabilities:
  package: package
```

Do not add tool-specific executors to Makefile MCP merely because a Docker image contains those tools.

## Repository-mounted vs image-baked policy

### Mount the repository

Use when development velocity matters and the host repository is the source of truth.

```text
image: Makefile MCP + toolchain
mount: Makefile + config + source
```

Changing `.makefile-mcp.yaml` still requires restarting the Makefile MCP process.

### Bake the repository contract

Use when reproducibility and deployment review matter more than live edits.

```text
image: Makefile MCP + toolchain + Makefile + .makefile-mcp.yaml + wrappers
```

This gives one immutable artifact for the callable contract and its runtime dependencies.

## User and filesystem permissions

The base image runs as non-root `makefile-mcp` (`10001:10001`). The development Compose setup deliberately overrides that identity with the host UID/GID for bind-mounted worktrees. For production, keep the base non-root user or another dedicated identity with only the filesystem permissions the recipes need.

Writable directories should be explicit. Do not grant broad host mounts, Docker socket access, privileged mode, or host networking unless a trusted recipe genuinely requires them; those privileges sit outside Makefile MCP's security boundary.

When Makefile MCP is PID 1 in a container, use an init process (`docker run --init` or Compose `init: true`) so orphaned recipe descendants are reaped correctly. Makefile MCP manages the task process group but is not a general-purpose process supervisor.

Lock files are created under:

```text
.makefile-mcp/locks/
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

Setting `inherit` replaces Makefile MCP's default `[PATH, HOME, USER]` list; it does not append to it. Keep the defaults explicitly when they are still required by recipes. `environment.allow` overrides inherited values with trusted configured literals.

Do not bake secrets into the image, Makefile, or `.makefile-mcp.yaml`. Scalar governed task inputs are also not a secret channel because they cross GNU Make as command-line assignments; use the deployment environment/secret mechanism for secrets.

Remember that trusted recipes can read inherited environment variables. See [Security](security.md#make-variables-and-process-environments).

## Validation before deployment

At minimum:

```bash
makefile-mcp doctor
makefile-mcp list
```

For a derived image:

```bash
docker run --rm my-makefile-mcp-runtime:1 doctor
docker run --rm my-makefile-mcp-runtime:1 list
```

For the Makefile MCP project itself:

```bash
make docker-check
```

## Production checklist

Before exposing a repository to an agent or orchestrator:

- [ ] repository Makefiles, included Make code, wrapper scripts, and provisioned tools are trusted;
- [ ] `.makefile-mcp.yaml` is present for non-trivial or shared agent use;
- [ ] `makefile-mcp doctor` exits cleanly;
- [ ] callable task inventory and dangerous-risk declarations have been reviewed;
- [ ] only required environment names are inherited or injected;
- [ ] the runtime user has only the filesystem permissions recipes require;
- [ ] `.makefile-mcp/locks` is writable by the runtime user;
- [ ] container execution uses an init process;
- [ ] MCP stdio is run without a pseudo-TTY;
- [ ] Docker socket, privileged mode, host networking, and broad host mounts are absent unless explicitly required;
- [ ] production image/tool versions or the deployed image digest are recorded.

## Network exposure

Makefile MCP does not expose an HTTP listener. The supported server runs over stdio. If another system wraps it in a network service, that wrapper owns authentication, authorization to reach the process, TLS, rate limiting, and network isolation.

Do not infer network safety from Makefile MCP's local stdio threat model.
