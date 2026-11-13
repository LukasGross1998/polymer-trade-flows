"""Command line of the pipeline: a registry from step names to the domains' step functions.

    uv run ptf ingest     # BACI trade data and sea distances (cached)
    uv run ptf clean      # BACI landing + dbt build -> data/warehouse.duckdb (trade marts)
    uv run ptf report     # docs/data_quality.md and charts
    uv run ptf model      # model layer, transport LP, docs/model_results.md
    uv run ptf portwatch  # PortWatch (incremental) + dbt build of the shipping marts
    uv run ptf market     # FRED prices and NY Fed GSCPI + dbt build of the market marts
    uv run ptf comtrade   # superseded own Comtrade download, for comparison (not in "all")
    uv run ptf all        # all steps except comtrade, in the order above

`uv run python -m ptf <step>` does the same. Each step is a plain function of the settings,
so Airflow (phase 5) can call the same functions as tasks. This module is the only place
that knows every domain; the domains do not know each other (ADR-012).
"""

import argparse
import logging
from collections.abc import Callable

from ptf.core.settings import Settings, get_settings
from ptf.legacy.comtrade import steps as comtrade_steps
from ptf.markets import steps as markets_steps
from ptf.model import steps as model_steps
from ptf.shipping import steps as shipping_steps
from ptf.trade import steps as trade_steps

Step = Callable[[Settings], None]

# Order matters: "all" runs these in this order (trade data before the model that reads it).
STEPS: dict[str, list[Step]] = {
    "ingest": [trade_steps.ingest, model_steps.ingest],
    "clean": [trade_steps.build],
    "report": [trade_steps.report],
    "model": [model_steps.run],
    "portwatch": [shipping_steps.refresh],
    "market": [markets_steps.refresh],
}

# Run only on request, never as part of "all" (ADR-009).
ON_REQUEST: dict[str, list[Step]] = {
    "comtrade": [comtrade_steps.run],
}


def steps_for(name: str) -> list[Step]:
    """The step functions behind a command-line step name, in execution order."""
    if name == "all":
        return [step for steps in STEPS.values() for step in steps]
    return {**STEPS, **ON_REQUEST}[name]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="ptf", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("step", choices=[*STEPS, *ON_REQUEST, "all"])
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    settings = get_settings()
    for step in steps_for(args.step):
        step(settings)


if __name__ == "__main__":
    main()
