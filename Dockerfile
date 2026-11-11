# Offline build from the committed fixtures: lint, unit tests, then dbt seed
# and build (all data tests included). No network access or API keys needed.
#   docker build -t pitwh . && docker run --rm pitwh
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project
COPY . .
RUN uv sync --locked

CMD ["make", "test", "build-fixtures"]
