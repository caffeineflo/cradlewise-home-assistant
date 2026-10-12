FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS runtime-base

ENV PATH="/app/.venv/bin:$PATH" \
    OPENSSL_armcap=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg liblzma5 openssl \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python*/ensurepip

FROM runtime-base AS build

COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /bin/

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
