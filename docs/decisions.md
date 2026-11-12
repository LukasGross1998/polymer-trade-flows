# Architecture Decision Records

Short records of significant decisions: context, decision, consequences.
New decisions are appended; superseded ones are marked, not deleted.

---

## ADR-001: Core tech stack

- **Date:** 2026-11-12
- **Status:** accepted

**Context.** A portfolio project that must show data engineering, optimisation and
production-grade software practices, run locally on a laptop and stay explainable line by line.

**Decision.**

| Concern | Choice | Why |
|---|---|---|
| Python and packages | Python 3.12, **uv** | One fast tool for Python versions, virtual envs and a lock file (`uv.lock`) -> reproducible installs locally and in CI. |
| Storage | **Parquet + DuckDB**, layers `raw -> clean -> model` | Columnar files are small and typed; DuckDB queries them with SQL without a server. The layering mirrors a lakehouse and keeps raw data immutable. |
| Optimisation | **Pyomo + HiGHS** | Pyomo writes the LP close to the maths and gives access to duals; HiGHS is a fast, free, open-source solver installable via pip (`highspy`). |
| App | **Dash + Plotly** | Interactive web app in pure Python; Plotly covers maps (`scattergeo`) and heatmaps. |
| Quality | **pytest, ruff, pre-commit**, type hints | ruff replaces flake8/isort/black in one tool; pre-commit enforces it before every commit; CI repeats the same checks. |
| Configuration | **pydantic-settings** + `.env` | Typed settings with validation; secrets stay in a git-ignored `.env` and are masked via `SecretStr`. |
| Packaging | `src/` layout, package `ptf` | Tests run against the installed package, not against loose files, which catches packaging errors early. |

**Consequences.** Dependencies are added only in the phase that needs them (no speculative
dependencies). Later phases add Docker, docker compose and Airflow.

---

## ADR-002: pandas instead of polars for data processing

- **Date:** 2026-11-12
- **Status:** accepted

**Context.** The data volume is small (a few hundred thousand rows of bilateral trade at most).
Both pandas and polars handle that easily, so performance is not the deciding factor.

**Decision.** Use **pandas**.

**Reasons.**
- **Ecosystem fit:** Plotly/Dash, Pyomo data handling, statsmodels and scikit-learn (phase 4)
  all accept pandas directly, so no conversions are needed at the boundaries.
- **Industry standard:** pandas is what most data science teams and interviewers expect;
  code reviews and pairing are easier.
- **Learning curve:** far more documentation and examples, which matters while learning the
  data stack.
- Heavy aggregations can be pushed down to **DuckDB SQL**, which offsets most of polars'
  advantages for this project size.

**Consequences / guardrails.** Use explicit dtypes when reading data, avoid relying on the
index (use plain columns and `reset_index()`), and prefer method chaining with clear names over
chained in-place assignment, to avoid pandas' common pitfalls (silent type changes,
`SettingWithCopyWarning`).
