"""Transport LP (SPEC section 4): supply every region's demand at minimum total cost.

    min  sum_ij unit_cost_ij * x_ij  +  sum_j penalty * u_j
    s.t. sum_j x_ij        <= capacity_i     for every supplying region i   (capacity)
         sum_i x_ij + u_j  >= demand_j       for every demand region j      (demand)
         x_ij >= 0, u_j >= 0

x_ij: tonnes shipped from i to j (x_ii = local supply), u_j: unmet demand in j.

Duals (shadow prices) are read from the solver:
- demand constraint of j: extra total cost of one more tonne of demand in j
  = marginal delivered cost = implied regional price (USD/t)
- capacity constraint of i: cost saving from one more tonne of capacity in i
  = scarcity rent of region i (USD/t); 0 if region i has idle capacity
"""

from dataclasses import dataclass

import pandas as pd
import pyomo.environ as pyo

from ptf.model.inputs import ModelInputs

SOLVER = "highs"


@dataclass
class TransportResult:
    status: str
    total_cost_usd: float
    flows: pd.DataFrame  # origin_region, dest_region, qty_t, unit_cost_usd_t
    regions: pd.DataFrame  # region, supply_t, capacity_t, demand_t, unmet_t, price, rent


def build_model(inputs: ModelInputs) -> pyo.ConcreteModel:
    """Translate the inputs into a Pyomo model; reads like the formulation above."""
    model = pyo.ConcreteModel(name="transport")
    model.R = pyo.Set(initialize=inputs.regions, ordered=True)

    model.x = pyo.Var(model.R, model.R, within=pyo.NonNegativeReals)  # tonnes i -> j
    model.u = pyo.Var(model.R, within=pyo.NonNegativeReals)  # unmet demand in j

    def total_cost(m: pyo.ConcreteModel) -> pyo.Expression:
        shipping = sum(inputs.unit_cost_usd_t(i, j) * m.x[i, j] for i in m.R for j in m.R)
        shortage = sum(inputs.penalty_usd_t * m.u[j] for j in m.R)
        return shipping + shortage

    model.cost = pyo.Objective(rule=total_cost, sense=pyo.minimize)

    def capacity(m: pyo.ConcreteModel, i: str) -> pyo.Expression:
        return sum(m.x[i, j] for j in m.R) <= inputs.capacity_t[i]

    def demand(m: pyo.ConcreteModel, j: str) -> pyo.Expression:
        return sum(m.x[i, j] for i in m.R) + m.u[j] >= inputs.demand_t[j]

    model.capacity = pyo.Constraint(model.R, rule=capacity)
    model.demand = pyo.Constraint(model.R, rule=demand)

    # Ask the solver to hand back the duals of all constraints.
    model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)
    return model


def solve(inputs: ModelInputs) -> TransportResult:
    """Build, solve with HiGHS and return flows, prices and rents as DataFrames."""
    model = build_model(inputs)
    result = pyo.SolverFactory(SOLVER).solve(model)
    status = str(result.solver.termination_condition)
    if status != "optimal":
        raise RuntimeError(f"transport LP not solved to optimality: {status}")

    flows = pd.DataFrame(
        [
            {
                "origin_region": i,
                "dest_region": j,
                "qty_t": pyo.value(model.x[i, j]),
                "unit_cost_usd_t": inputs.unit_cost_usd_t(i, j),
            }
            for i in model.R
            for j in model.R
        ]
    )
    flows["qty_t"] = flows["qty_t"].clip(lower=0.0)  # remove solver noise like -1e-12

    regions = pd.DataFrame(
        [
            {
                "region": r,
                "capacity_t": inputs.capacity_t[r],
                "supply_t": sum(pyo.value(model.x[r, j]) for j in model.R),
                "demand_t": inputs.demand_t[r],
                "unmet_t": pyo.value(model.u[r]),
                "prod_cost_usd_t": inputs.prod_cost_usd_t[r],
                # >= constraint in a minimisation: dual >= 0 = marginal cost of demand.
                "price_usd_t": model.dual[model.demand[r]],
                # <= constraint in a minimisation: dual <= 0; the rent is its magnitude.
                "rent_usd_t": -model.dual[model.capacity[r]],
            }
            for r in model.R
        ]
    )
    regions["utilisation"] = regions["supply_t"] / regions["capacity_t"]

    return TransportResult(
        status=status,
        total_cost_usd=pyo.value(model.cost),
        flows=flows,
        regions=regions,
    )
