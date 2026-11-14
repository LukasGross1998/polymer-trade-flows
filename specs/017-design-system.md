# 017 – One design: theme, KPI tile, global bar, number formats, method panels

- **Status:** draft
- **Branch / PR:** `feat/design-system` / see PR
- **SPEC.md sections:** 7 (app); phase 3 of the user's dashboard plan (14 Nov 2026)

## Goal

All tabs look and read the same: colours carry one meaning each, every key figure sits in
the same tile with unit, period and data date, the global choices (route scenario, grade,
currency) live in one bar that every tab follows, numbers are formatted the same way, and
explanations sit behind an info icon instead of footnotes. No developer text in the UI.

## Acceptance criteria

1. **Central theme** (`ptf.app.theme`, replaces `style.py` constants used by the tabs):
   - *status colours* only for status (ok / watch / elevated / critical, plus "at risk",
     "detour", "not sourceable"), always with an icon and a word;
   - a *categorical palette* for data series and cost components, assigned in a fixed order,
     validated with the data-viz palette validator (colour-blind separation, contrast on the
     card surface) in light mode;
   - a *route encoding* used by every chart that shows origins or routes (Sankey, supplier
     chart, landed cost, planner): open / detour / at risk / not sourceable, the same colours
     and labels everywhere;
   - one Plotly template (font, colours, grid, hover) registered as the default, so no tab
     sets fonts or colours itself.
   Test: no tab module contains a hex colour; status colours are not in the categorical
   palette; the template is the Plotly default.

2. **KPI tile component** (`theme.tile` / `charts.kpi`), used by all tabs: label, value,
   unit, delta against a standard period, data date, optional status (icon + word) and
   optional sparkline. Standard period: 30 days for daily series, 1 month for monthly ones,
   "n/a" for annual data (no delta). Tiles that are not figures go away: "Basis USD/EUR"
   becomes a footnote line in the method panel. Test: a daily series 100 → 103 over 30 days
   gives "+3.0 % vs. 30 days"; a monthly series shows the change to the previous month; each
   tile shows its data date.

3. **Global bar** below the header: route scenario (spec 014), PE grade, currency (EUR /
   USD). Stored in `dcc.Store`s with session persistence, read by every tab that uses them;
   the per-tab grade dropdowns (sourcing, landed cost, planner) and the currency switch of
   the prices tab are removed. Landed cost and planner show values in the chosen currency.
   Test: changing the grade in the bar changes sourcing, landed cost and planner; the tabs
   no longer define their own grade or currency controls.

4. **Tabs:** the second level (Situation … Order planner) as underline tabs with less
   height; the first level stays as it is.

5. **Typography and numbers** (`theme.fmt`):
   - one font family for the UI and Plotly;
   - chart titles as card titles above the plot (not inside the Plotly figure);
   - numbers: true minus sign (U+2212), thousands separator, compact money with the
     currency symbol ("€197k", "$1.2m"), units after the number with a thin space, percent
     with one decimal where below 10 %, ranges with an en dash.
   Test: `fmt.money(-197_400, "EUR")` = "−€197k"; `fmt.pct(3.26)` = "+3.3 %"; signed numbers
   use U+2212.

6. **One period per tab:** where a tab has a period choice, it applies to all of its time
   charts (prices: all charts; chokepoints and ports already have one). Test: the prices
   tab's charts share the period's start date.

7. **Method panel instead of footnotes:** each tab's footnote moves behind an info icon (i)
   next to the tab's first heading, as a collapsible "Method and sources" panel; the data
   dates and sources stay there. Developer hints (e.g. "run `uv run ptf clean`") are
   replaced by plain messages ("No trade data loaded yet – use Update data"). Region codes
   and abbreviations are written out or get a tooltip: MDE → Middle East, NAM → North and
   Central America, nm → nautical miles, kt → thousand tonnes, TEU, FOB, CIF.
   Test: no text in `ptf.app` contains "uv run" or "ptf "; region codes in charts are
   replaced by region names.

8. Quality gates as usual; screenshots of the tabs checked locally; README figures updated.

## Out of scope

- New charts or changed chart types (phase 4: spread chart, timeline, table with inline
  bars, …).
- Dark mode.
- New data (phase 5).

## Design notes

- `ptf.app.theme`: palette, status and route encodings, Plotly template, `tile()`,
  `info()`, `method_panel()`; `ptf.app.fmt`: number formatting. `style.py` stays only as a
  thin alias during the change, then goes.
- The global bar replaces the header's scenario dropdown (spec 014); stores:
  `global-scenario`, `global-grade`, `global-currency`.
- Currency conversion uses the existing FX series (FRED `DEXUSEU`); the landed view already
  computes USD and EUR columns.
- Palette: start from the data-viz skill's validated default palette and check it with its
  validator; status colours keep their current meaning (green / yellow / orange / red).
- Files: `src/ptf/app/{theme,fmt,charts,__main__,data}.py`, all tab modules, tests
  (`test_app.py`, new `test_theme.py`), README screenshots.
- Open question for the user: keep the four-level traffic-light colours as they are
  (green / yellow / orange / red) – proposed yes.
