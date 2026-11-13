# 005 – Docker image and compose

- **Status:** done
- **Branch / PR:** `chore/docker` / see PR
- **SPEC.md sections:** 9 (architecture), 10 (next steps, step 4); ADR-013

## Goal

The project runs in a container: one image, built with uv in several stages, holds code,
configuration and the dbt project. `docker compose` starts the dashboard and runs pipeline
steps against the local `data/` folder. Code and environment are the same on every machine,
in CI and later in Airflow (step 5); data stay outside the image.

## Acceptance criteria

1. **Settings instead of assumptions about the machine.** Host and port of the app and the
   location of the dbt project are settings with today's values as defaults:
   - `APP_HOST` (default `127.0.0.1`), `APP_PORT` (default `8050`);
   - `DBT_PROJECT_DIR` (default: the repository's `dbt/` folder).
   Locally nothing changes; tests check defaults and overrides from the environment.
2. **dbt writes only where it may.** dbt's `target/` and `logs/` go to a writable folder
   (`DBT_TARGET_PATH`, `DBT_LOG_PATH`); the dbt project folder in the image can be read-only.
3. **Image.** `docker build -t ptf .` builds a multi-stage image:
   - stage *builder*: uv, `uv sync --locked --no-dev`, the project installed into `.venv`;
   - stage *runtime*: `python:3.12-slim` with that `.venv`, `config/` and `dbt/`, no uv, no
     compilers, no tests; runs as a non-root user; working directory `/app`.
   Changing only Python code reuses the cached dependency layer.
4. **Nothing private or bulky in the image.** A `.dockerignore` keeps out `data/`, `.env`,
   `.venv`, `.git`, `tests/`, `notebooks/`, caches. Checked in CI: the image contains no
   `/app/data` with files and no `.env`.
5. **App in a container.** `docker compose up app` serves the dashboard on
   `http://localhost:8050` from the warehouse in `./data` (volume); a healthcheck reports
   the container as healthy once the page answers with HTTP 200.
6. **Pipeline in a container.** `docker compose run --rm pipeline <step>` runs any step of
   `ptf` (same names as locally) on the same volume, e.g. `model` gives the same result as
   locally (explained share 42 %, total cost 104.5 bn USD). Generated reports go to `./docs`.
7. **CI.** A second GitHub Actions job builds the image and runs a smoke test:
   `ptf --help` in the container, and the app container becomes healthy (HTTP 200) although
   CI has no warehouse (see design notes, "smoke test without data").

## Out of scope

- Airflow (step 5), pushing to a registry, deployment to a cloud (ECR/ECS), Kubernetes.
- Downloading data inside the image build: data come from the volume or from `ptf ingest`.
- Running the app with several worker processes (the app keeps one in-memory state).

## Design notes

- Files: `Dockerfile`, `.dockerignore`, `compose.yaml`, CI job in
  `.github/workflows/ci.yml`; `core/settings.py`, `core/warehouse.py` (dbt path from the
  settings, dbt output paths), `app/__main__.py` (host and port from the settings).
- **Web server:** today `Dash.run()` uses Flask's development server, which prints "do not
  use in production". In the container the app runs under **gunicorn** (one worker, several
  threads; `ptf.app` exposes the Flask `server`). Locally `python -m ptf.app` stays as is.
  New dependency: `gunicorn`.
- **Volumes:** `./data:/app/data` for both services; `./docs:/app/docs` for the pipeline
  (reports). `.env` reaches the containers via `env_file` (optional, no key is needed).
- **Writable paths for the non-root user:** dbt output and the matplotlib cache
  (`MPLCONFIGDIR`) under `/tmp`; data and docs on the volumes.
- **User and file ownership:** files written into `./data` from the container belong to the
  container user; on macOS Docker Desktop maps them to your user, on Linux the compose file
  sets the user id. To verify during implementation.
- **Platforms:** the Mac builds `linux/arm64`, GitHub Actions `linux/amd64`; all
  dependencies (duckdb, highspy, pyarrow, dbt) ship wheels for both. No multi-platform
  build needed yet.
- **Smoke test without data (criterion 7):** CI has no warehouse. The app currently requires
  `mart_chokepoint_transits` (`require()` fails). Either the smoke test builds the fixture
  warehouse in the container first, or the app shows a start page "no data yet: run
  `ptf portwatch`" without a warehouse. Proposal: the second option, a small change that
  also helps a fresh clone. To decide before implementation.
- Image size is measured and written into ADR-013 (expected: several hundred MB, mostly
  dbt, pandas, pyarrow, matplotlib).
- ADR-013 records the decisions (multi-stage with uv, gunicorn, data on volumes,
  non-root); README gets a section "Run with Docker"; CHANGELOG under "Unreleased".
