FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6

COPY --from=ghcr.io/astral-sh/uv:0.11.19@sha256:b46b03ddfcfbf8f547af7e9eaefdf8a39c8cebcba7c98858d3162bd28cf536f6 /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg openssl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY packages/cradlewise-client ./packages/cradlewise-client
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra observability --no-install-project

COPY cradlewise_local ./cradlewise_local
COPY stream_local.py cradlewise_api.py ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra observability \
    && test -x /app/.venv/bin/cradlewise-pin-mqtt-ca
RUN groupadd --gid 10001 cradlewise \
    && useradd --uid 10001 --gid cradlewise --home-dir /app --no-create-home cradlewise \
    && chown -R cradlewise:cradlewise /app

USER 10001:10001

HEALTHCHECK --interval=15s --timeout=5s --start-period=45s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/live', timeout=3).read()"]

ENTRYPOINT ["python", "-m", "cradlewise_local"]
