FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends make ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/make-mcp
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

WORKDIR /workspace
ENTRYPOINT ["make-mcp"]
CMD ["serve"]
