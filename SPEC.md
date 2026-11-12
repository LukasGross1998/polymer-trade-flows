# SPEC: Polymer Trade Flow & Disruption Simulator

Status: v0.1 (Entwurf) – wird in jeder Phase verfeinert.

## 1. Ziel

Ein reproduzierbares Modell, das

1. die beobachteten globalen Handelsströme von **Polyethylen (HS 3901)** aus offiziellen Statistiken aufbereitet,
2. diese Ströme mit einem **kostenminimierenden Transportmodell (LP)** erklärt,
3. die Wirkung von **Störungen** auf Ströme, Kosten und regionale Preisaufschläge quantifiziert,
4. alles in einer **interaktiven Dash-App** zugänglich macht.

### Zielnutzer (fiktiv)
Ein Analyst oder Trader im Chemiemarkt, der fragt: *„Was passiert mit den PE-Strömen nach Europa, wenn das Rote Meer gesperrt ist – und wer gewinnt Marktanteile?“*

### Nicht-Ziele (vorerst)
- Keine Preisprognose auf Tagesbasis
- Keine Unterscheidung von PE-Qualitäten (LDPE/LLDPE/HDPE) im MVP – evtl. später über HS-6-Codes 390110/390120/390140
- Keine kommerziellen Datenquellen

## 2. Datenquellen

| Quelle | Inhalt | Zugang | Phase |
|---|---|---|---|
| UN Comtrade | Bilaterale Handelsmengen (kg) und -werte (USD), monatlich/jährlich, HS 3901 | API mit kostenlosem Key | 1 |
| Eurostat Comext | EU-Handel, detaillierter, als Abgleich | öffentliche API/Bulk | 1 (optional) |
| Seewege/Distanzen | Distanz zwischen repräsentativen Häfen je Region | Python-Paket `searoute` | 1 |
| Brent-Ölpreis | Treiber für Rohstoff- und Bunkerkosten | EIA oder FRED | 1 |
| Kapazitäten/Kosten | Regionale PE-Kapazität und Cash-Kosten | **Annahmen** aus öffentlichen Quellen, klar gekennzeichnet | 2 |

API-Details (Endpunkte, Limits, Parameter) vor der Implementierung in der aktuellen Doku prüfen.

### Startumfang
- Jahre: 2019–letztes vollständiges Jahr
- Frequenz: zuerst jährlich, später monatlich
- Länder: die ca. 25–30 größten Exporteure/Importeure, gruppiert in **8–10 Modellregionen** (z. B. Nordamerika, Südamerika, Westeuropa, Naher Osten, China, Nordostasien ohne China, Südostasien, Indien, Afrika) – Zuordnung in `config/regions.yaml`

## 3. Datenpipeline

### Layer
- **raw:** API-Antworten unverändert als Parquet, mit Abrufzeitpunkt
- **clean:** einheitliches Schema, Einheiten normiert (Tonnen, USD)
- **model:** Region-zu-Region-Matrizen, Inputs für das LP

### Clean-Schema (Minimum)
`year, month, reporter_iso3, partner_iso3, flow (import|export), hs_code, qty_t, value_usd, source, is_imputed, imputation_method`

### Qualitätsregeln
1. Einheitswerte (USD/t) berechnen; Ausreißer markieren (z. B. außerhalb eines robusten Bandes pro Jahr/Region).
2. **Spiegelstatistik:** Export A→B vs. Import B←A vergleichen. Abweichung messen und dokumentieren.
3. **Abgleich-Regel (MVP):** Importmeldungen bevorzugen (CIF, meist zuverlässiger), Export als Fallback; Mengen ohne Gewicht über Wert ÷ regionalen Einheitswert imputieren.
4. Jede Imputation setzt `is_imputed=True` und nennt die Methode.
5. Data-Quality-Report (Abdeckung, Abweichungen, Imputationsanteil) als Tabelle/Grafik.

## 4. Optimierungsmodell (Transport-LP)

### Mengen
- `R`: Regionen; `i ∈ R` Angebotsregion, `j ∈ R` Nachfrageregion

### Parameter
- `cap_i`: Produktionskapazität (t/Jahr) – Annahme
- `prod_cost_i`: Produktionskosten (USD/t) – Annahme, optional an Brent gekoppelt
- `dem_j`: Nachfrage (t/Jahr) – abgeleitet aus Produktion + Importe − Exporte (scheinbarer Verbrauch) bzw. vereinfacht
- `dist_ij`: Seedistanz (nm)
- `freight_ij`: Frachtkosten (USD/t) = fix + variabel × Distanz (Parameter in Config)
- `tariff_ij`: Zollaufschlag (USD/t oder %), Standard 0

### Entscheidungsvariable
- `x_ij ≥ 0`: Menge von i nach j (t); `x_ii` = lokale Versorgung (Frachtkosten ≈ 0)

### Ziel
min Σ_ij (prod_cost_i + freight_ij + tariff_ij) · x_ij

### Nebenbedingungen
- Kapazität: Σ_j x_ij ≤ cap_i  ∀ i
- Nachfrage: Σ_i x_ij ≥ dem_j  ∀ j

### Auswertung
- Optimale Ströme vs. beobachtete Ströme (Matrixvergleich, Kennzahlen z. B. Anteil korrekt erklärter Menge)
- **Duals der Nachfrage-Constraints** = marginale Versorgungskosten je Region → als implizite regionale Preise interpretieren
- Duals der Kapazitäts-Constraints = Knappheitsrente

### Kalibrierung (Phase 2b)
Abweichungen zwischen Modell und Realität sind erwartbar (Verträge, Qualitäten, Zölle, Integration). Schritt 1: dokumentieren. Schritt 2 (optional): Kalibrierungsaufschläge je Route schätzen oder Entropie-/Gravitationsansatz als Vergleich.

## 5. Szenarien

In `config/scenarios.yaml` deklarativ definiert, z. B.:

| ID | Beschreibung | Umsetzung |
|---|---|---|
| `base` | Status quo | – |
| `red_sea_closed` | Kein Suez/Rotes Meer | Distanzen über Kap der Guten Hoffnung neu berechnen |
| `panama_drought` | Eingeschränkter Panamakanal | Aufschlag oder Umroutung betroffener Routen |
| `tariff_us_cn` | Zoll zwischen USA und China | `tariff_ij` setzen |
| `plant_outage` | Ausfall in einer Region | `cap_i` reduzieren |
| `oil_shock` | Brent +50 % | Kosten- und Frachtparameter skalieren |

Ausgabe pro Szenario: Δ Ströme, Δ Gesamtkosten, Δ regionale Schattenpreise, Gewinner/Verlierer.

### Kostenkurve
Pro Szenario eine globale Angebotskurve (Regionen nach Kosten sortiert, Breite = Kapazität) mit Nachfrage-Linie.

## 6. Prognose (optional, Phase 4)
- Ziel: jährliche/monatliche Importmenge je Region
- Erst Baselines (naiv, saisonal-naiv), dann Gradient Boosting mit Features (Brent, Lags, Saison)
- Zeitlich korrekte Validierung (rolling origin), Metrik MAPE/MAE, ehrlicher Vergleich mit Baseline

## 7. Dash-App

### Seiten/Tabs
1. **Datenqualität:** Abdeckung, Spiegelabweichungen, Imputationsanteil
2. **Beobachtete Ströme:** Weltkarte mit Strompfeilen (Plotly `scattergeo`), Filter Jahr/Region
3. **Modell vs. Realität:** Vergleichsmatrix/Heatmap, Kennzahlen
4. **Szenarien:** Szenario wählen, Parameter per Slider (Frachtsatz, Zoll, Kapazität), Vorher/Nachher-Karte, Tabelle Δ Schattenpreise, Kostenkurve

### Akzeptanzkriterien
- App startet mit einem Befehl lokal und in Docker
- Szenario-Neuberechnung < 5 s
- Keine Geschäftslogik in Callbacks (nur Aufrufe von `src/ptf/...`)

## 8. Engineering

- Tests: Ingest mit gespeicherten Fixtures (keine Live-API in Tests), Bereinigungsregeln, LP mit Mini-Beispiel (3 Regionen, Ergebnis per Hand nachrechenbar), Szenario-Konfiguration
- CI mit GitHub Actions: ruff + pytest
- Docker: ein Image für Pipeline + App; `docker compose` für App und später Airflow
- Airflow-DAG: monatlich `ingest → clean → build_model_inputs → solve_scenarios → publish`
- Doku: README (Problem, Ansatz, Screenshots, Ergebnisse, Grenzen, How-to-run), `docs/methodology.md`, `docs/decisions.md`

## 9. Phasen

| Phase | Inhalt | Ergebnis |
|---|---|---|
| 0 | Repo-Grundgerüst, Tooling, CI | leeres, sauberes Projekt, grüne Pipeline |
| 1 | Ingest + Bereinigung + DQ-Report | `clean`-Layer, Spiegelstatistik-Analyse |
| 2 | Transport-LP, Vergleich mit Realität, Duals | erstes erklärbares Modell |
| 3 | Szenarien, Kostenkurve, Dash-App | **bewerbungstaugliches MVP** |
| 4 | Prognose (optional) | Baseline vs. ML |
| 5 | Docker, Airflow, Feinschliff README | produktionsnahes Portfolio |

## 10. Offene Fragen
- Woher kommen plausible Kapazitäts- und Kostenannahmen je Region? (öffentliche Berichte, Unternehmenspräsentationen – Quellen dokumentieren)
- Jährlich oder monatlich für das LP-MVP? (Vorschlag: jährlich)
- polars oder pandas?
