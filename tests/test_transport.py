"""Transport LP on a 3-region example that can be solved by hand.

Regions: A (cheap producer), B (mid), C (expensive).

    production cost  A 500, B 800, C 1000 USD/t
    capacity         A 60,  B 100, C 100 t
    demand           A 20,  B 40,  C 50 t      (total 110 > A's capacity 60)
    freight          A-B 50, A-C 100, B-C 60 USD/t (same in both directions), 0 within

Delivered cost to each destination (cheapest first):
    to A: from A 500, from B 850, from C 1100
    to B: from A 550, from B 800, from C 1060
    to C: from A 600, from B 860, from C 1000

A's 60 t go where they save most against the next-best source:
    A: 850 - 500 = 350,   C: 860 - 600 = 260,   B: 800 - 550 = 250
-> A->A 20, A->C 40 (A is full), C's remaining 10 from B (860 < 1000), B->B 40.
Total cost = 20*500 + 40*600 + 40*800 + 10*860 = 74,600 USD.

Duals by hand:
- B has idle capacity (50 of 100 t used): B is the marginal supplier, rent B = 0.
- price B = 800 (one more tonne in B comes from B's idle capacity).
- price C = 860 (one more tonne in C comes from B).
- rent A = 260: one more tonne of A capacity replaces a B->C tonne (860) by A->C (600).
- price A = 760: one more tonne in A comes from A (500), and the tonne A no longer sends to C
  is replaced by B (+860 - 600), so 500 + 260 = 760 (cheaper than shipping B->A for 850).
"""

import pytest

from ptf.model.inputs import ModelInputs
from ptf.model.transport import TransportResult, solve

FREIGHT = {"AB": 50.0, "AC": 100.0, "BC": 60.0}


def freight(i: str, j: str) -> float:
    if i == j:
        return 0.0
    return FREIGHT["".join(sorted(i + j))]


def three_regions(capacity_a: float = 60.0, penalty: float = 5000.0) -> ModelInputs:
    regions = ["A", "B", "C"]
    routes = [(i, j) for i in regions for j in regions]
    return ModelInputs(
        regions=regions,
        capacity_t={"A": capacity_a, "B": 100.0, "C": 100.0},
        demand_t={"A": 20.0, "B": 40.0, "C": 50.0},
        prod_cost_usd_t={"A": 500.0, "B": 800.0, "C": 1000.0},
        freight_usd_t={(i, j): freight(i, j) for i, j in routes},
        tariff_usd_t={route: 0.0 for route in routes},
        penalty_usd_t=penalty,
    )


@pytest.fixture(scope="module")
def result() -> TransportResult:
    return solve(three_regions())


def test_flows_match_hand_solution(result: TransportResult) -> None:
    shipped = result.flows[result.flows["qty_t"] > 1e-6]
    flows = {
        (o, d): q
        for o, d, q in zip(shipped.origin_region, shipped.dest_region, shipped.qty_t, strict=True)
    }

    assert flows == pytest.approx({("A", "A"): 20, ("A", "C"): 40, ("B", "B"): 40, ("B", "C"): 10})
    assert result.total_cost_usd == pytest.approx(74_600)


def test_regional_prices_are_marginal_delivered_costs(result: TransportResult) -> None:
    prices = result.regions.set_index("region")["price_usd_t"]

    assert prices.to_dict() == pytest.approx({"A": 760, "B": 800, "C": 860})


def test_scarcity_rent_only_for_the_full_low_cost_region(result: TransportResult) -> None:
    rents = result.regions.set_index("region")["rent_usd_t"]

    assert rents.to_dict() == pytest.approx({"A": 260, "B": 0, "C": 0})


def test_price_gap_equals_cost_on_used_routes(result: TransportResult) -> None:
    # Spatial arbitrage: where A ships to C, price C = cost in A + rent A + freight A->C.
    regions = result.regions.set_index("region")

    assert regions.loc["C", "price_usd_t"] == pytest.approx(500 + 260 + 100)


def test_missing_capacity_shows_up_as_unmet_demand_priced_at_penalty() -> None:
    inputs = three_regions()
    inputs.capacity_t = {"A": 10.0, "B": 10.0, "C": 10.0}  # 30 t for 110 t of demand

    result = solve(inputs)
    regions = result.regions.set_index("region")

    assert regions["unmet_t"].sum() == pytest.approx(80)
    assert regions["price_usd_t"].max() == pytest.approx(5000)  # capped by the penalty
