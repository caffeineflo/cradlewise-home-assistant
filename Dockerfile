FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS runtime-base

ENV PATH="/app/.venv/bin:$PATH" \
    OPENSSL_armcap=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg openssl \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python*/ensurepip

FROM runtime-base AS build

COPY --from=ghcr.io/astral-sh/uv:0.12.12@sha256:73d2665b478d8fa2de1cf105c6841f8e9cb6b09e568fc7700440c09f8fcd7ac4 /uv /bin/

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY packages/cradlewise-client ./packages/cradlewise-client
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra observability --no-install-project

COPY cradlewise_local ./cradlewise_local
COPY stream_local.py cradlewise_api.py ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra observability \
    && test -x /app/.venv/bin/cradlewise-pin-mqtt-ca \
    && python -c "import aiortc, boto3, cryptography.x509, cradlewise_local"

FROM runtime-base AS runtime

WORKDIR /app
COPY --from=build --chown=10001:10001 /app /app
RUN groupadd --gid 10001 cradlewise \
    && useradd --uid 10001 --gid cradlewise --home-dir /app --no-create-home cradlewise

USER 10001:10001

HEALTHCHECK --interval=15s --timeout=5s --start-period=45s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/live', timeout=3).read()"]

ENTRYPOINT ["python", "-m", "cradlewise_local"]
