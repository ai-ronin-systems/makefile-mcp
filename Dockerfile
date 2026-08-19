FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/makefile-mcp

RUN apt-get update \
    && apt-get install -y --no-install-recommends make ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 makefile-mcp \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/makefile-mcp --shell /usr/sbin/nologin makefile-mcp

WORKDIR /opt/makefile-mcp
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN mkdir -p /workspace && chown makefile-mcp:makefile-mcp /workspace
WORKDIR /workspace
USER makefile-mcp
ENTRYPOINT ["makefile-mcp"]
CMD ["serve"]
