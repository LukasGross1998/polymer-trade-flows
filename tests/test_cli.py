"""The pipeline command line dispatches to the right step functions."""

import pytest

from ptf import pipeline

STEPS = ["run_ingest", "run_clean", "run_report", "run_model", "run_portwatch", "run_market"]


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace every step function by a stub that records its name."""
    called: list[str] = []
    for name in [*STEPS, "run_comtrade"]:
        monkeypatch.setattr(pipeline, name, lambda *args, _n=name, **kwargs: called.append(_n))
    return called


def test_single_step(calls: list[str]) -> None:
    pipeline.main(["model"])

    assert calls == ["run_model"]


def test_all_runs_every_step_in_order_but_not_the_comtrade_check(calls: list[str]) -> None:
    pipeline.main(["all"])

    assert calls == STEPS


def test_comtrade_check_only_on_request(calls: list[str]) -> None:
    pipeline.main(["comtrade"])

    assert calls == ["run_comtrade"]


def test_unknown_step_is_rejected() -> None:
    with pytest.raises(SystemExit):
        pipeline.main(["deploy"])
