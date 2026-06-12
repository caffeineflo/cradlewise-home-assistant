FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY cradlewise_local ./cradlewise_local
COPY stream_local.py cradlewise_api.py ./

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["cradlewise-local"]
