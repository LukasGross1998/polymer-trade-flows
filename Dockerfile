# syntax=docker/dockerfile:1
# Image of the project (ADR-013): code, configuration and the dbt project; data stay outside
# (volume ./data). Two stages: "builder" installs the dependencies with uv, "runtime" only
# receives the finished environment - no uv, no build tools, no tests.
#
#   docker build -t ptf .
#   docker compose up app                     # dashboard on http://localhost:8050
#   docker compose run --rm pipeline model    # any `ptf` step

ARG PYTHON_IMAGE=python:3.12-slim
# Optional dependency groups, e.g. "--extra asia" for the isolated AKShare image ptf:asia
# (spec 012, ADR-015). Empty for the normal image ptf:local.
ARG EXTRAS=""

# --- stage 1: builder ----------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS builder
ARG EXTRAS

# uv as a single binary from its official image, same version as uv.lock was written with.
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

# Compile .py to .pyc once at build time (faster start); copy files instead of hard links
# (the cache is a separate mount); use the image's Python, never download one.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# 1) Dependencies only. This layer depends on pyproject.toml and uv.lock alone, so changing
#    Python code does not reinstall pandas, dbt & co. (Docker layer cache).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project ${EXTRAS}

# 2) The project itself, installed as a regular package (not linked to the source folder).
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable ${EXTRAS}

# --- stage 2: runtime ----------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

# An unprivileged user: a process that breaks out of the app is not root in the container.
RUN groupadd --system ptf && useradd --system --gid ptf --create-home ptf

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY config ./config
COPY dbt ./dbt

# PATH: the environment's programs (ptf, dbt, gunicorn) come first.
# DBT_*: dbt writes target/ and logs/ to /tmp, the dbt folder in the image stays read-only.
# MPLCONFIGDIR: matplotlib needs a writable cache folder.
# APP_HOST: listen on all interfaces of the container, so the published port reaches the app.
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    DBT_PROJECT_DIR=/app/dbt \
    DBT_TARGET_PATH=/tmp/dbt/target \
    DBT_LOG_PATH=/tmp/dbt/logs \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    MPLCONFIGDIR=/tmp/matplotlib \
    APP_HOST=0.0.0.0 \
    APP_PORT=8050

USER ptf
EXPOSE 8050

# Healthy once the page answers; python instead of curl, which the slim image does not have.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8050/', timeout=4)"]

# One worker process (the app holds its data in memory), several threads for requests.
CMD ["gunicorn", "--bind", "0.0.0.0:8050", "--workers", "1", "--threads", "4", "--timeout", "120", "ptf.app.wsgi:server"]
