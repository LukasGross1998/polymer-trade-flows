"""The command line maps step names to the domains' step functions."""

import pytest

from ptf import cli
from ptf.legacy.comtrade import steps as comtrade_steps
from ptf.markets import steps as markets_steps
from ptf.model import steps as model_steps
from ptf.shipping import steps as shipping_steps
from ptf.trade import steps as trade_steps

ALL_IN_ORDER = [
    trade_steps.ingest,
    model_steps.ingest,
    trade_steps.build,
    trade_steps.report,
    model_steps.run,
    shipping_steps.refresh,
    markets_steps.refresh,
]


def test_all_runs_every_step_in_order_but_not_the_comtrade_check() -> None:
    assert cli.steps_for("all") == ALL_IN_ORDER
    assert comtrade_steps.run not in cli.steps_for("all")


def test_single_steps() -> None:
    assert cli.steps_for("model") == [model_steps.run]
    assert cli.steps_for("ingest") == [trade_steps.ingest, model_steps.ingest]
    assert cli.steps_for("comtrade") == [comtrade_steps.run]
    assert cli.steps_for("dce") == [markets_steps.download_dce]
    assert markets_steps.download_dce not in cli.steps_for("all")


def test_main_runs_the_selected_steps_with_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setitem(cli.STEPS, "model", [lambda settings: called.append("model")])

    cli.main(["model"])

    assert called == ["model"]


def test_unknown_step_is_rejected() -> None:
    with pytest.raises(SystemExit):
        cli.main(["deploy"])
