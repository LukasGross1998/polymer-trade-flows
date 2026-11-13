# 001 – Quality gates and working agreement

- **Status:** done
- **Branch / PR:** `chore/quality-gates`
- **SPEC.md sections:** 8 (engineering)

## Goal

Make AI-assisted development reviewable and safe: every change goes through a branch, a PR
and automatic checks, and the checks cover types and test coverage, not only lint and tests.

## Acceptance criteria

1. `uv run mypy` runs in strict mode (except `warn_return_any`) and reports no errors.
2. CI fails if mypy fails or test coverage drops below 85 %.
3. The same mypy check runs as a pre-commit hook.
4. No test module imports another test module; shared fakes live in `tests/helpers.py`.
5. BACI and GSCPI downloads and the pipeline command line are covered by tests
   (including an interrupted download that must not leave a "complete" file).
6. `CLAUDE.md` contains the branch/PR workflow and a Definition of Done; a PR template
   repeats the checklist.
7. The state before this change is tagged `v0.3.0`; `CHANGELOG.md` exists.

## Out of scope

Restructuring packages, dbt/DuckDB data model, Docker, Airflow (later steps, see ADR-010).
