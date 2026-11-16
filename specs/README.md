# Feature specs

One short spec per change that is more than a typo (ADR-010). Copy `TEMPLATE.md` to
`NNN-short-name.md` (next free number), agree on the acceptance criteria before coding,
and link the PR. `SPEC.md` remains the overall specification; these files record the
increments.

| No. | Spec | Status |
|---|---|---|
| 001 | [Quality gates and working agreement](001-quality-gates.md) | done |
| 002 | [dbt warehouse: trade data](002-dbt-trade-model.md) | done |
| 003 | [dbt warehouse: shipping and market data](003-dbt-shipping-markets.md) | done |
| 004 | [Package structure by domain](004-package-by-domain.md) | done |
| 005 | [Docker image and compose](005-docker.md) | done |
| 006 | [Buyer dashboard: situation, prices, sourcing exposure](006-buyer-dashboard.md) | done |
| 007 | [Landed cost by supplier country](007-landed-cost.md) | done |
| 008 | [Breakdown by class: commodities, vessels, PE grades](008-class-breakdown.md) | done |
| 009 | [Marine weather, official EU duties, nautical chart layer](009-weather-duties-seamap.md) | done |
| 010 | [Order planner: landed cost against arrival date](010-order-planner.md) | done |
| 011 | [Daily LLDPE price from the Dalian futures exchange (AKShare)](011-dce-lldpe-futures.md) | done |
| 012 | [Isolated container for the AKShare download, latest intraday quote](012-asia-container-intraday.md) | done |
| 013 | [Situation page for European PE buyers](013-situation-redesign.md) | done |
| 014 | [Route scenarios: availability vs. transit risk, one scenario for all tabs](014-route-scenarios.md) | done |
| 015 | [Source audit: every number about the world has a source](015-source-audit.md) | done |
| 016 | [Recommendation logic: sourceable origins, confidence, price ranges, order timing](016-recommendation-logic.md) | done |
| 017 | [One design: theme, KPI tile, global bar, number formats, method panels](017-design-system.md) | done |
| 018 | [Charts that answer the buyer's question](018-charts.md) | done |
