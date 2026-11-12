# SPEC: Polymer Trade Flow & Disruption Simulator

Status: v0.3 (Entwurf) – wird in jeder Phase verfeinert.

Änderungen v0.3 (Phase 1): Comtrade ein Jahr pro Abfrage, ISO-Codes aus Referenztabellen, `qty_estimated_by_source`, Brent über FRED, drei Clean-Tabellen, konkrete Ausreißerregel, Häfen in `regions.yaml`, Regionen festgelegt.

Änderungen v0.2 (Phase 0): Nachfrage-Definition, Schlupfvariable für ungedeckte Nachfrage, Vergleich nur interregionaler Ströme, Jahre 2019–2024, Region „Rest der Welt“, Zoll in USD/t, Comtrade-Filter, Spiegelstatistik über Mengen, offene Fragen beantwortet.

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
  - Bekannte Grenze: HS 3901 enthält auch EVA-Copolymere (390130) und sonstige Ethylen-Polymere (390190). Das MVP nutzt HS 3901 gesamt und dokumentiert das in `docs/methodology.md`.
- Keine kommerziellen Datenquellen

## 2. Datenquellen

| Quelle | Inhalt | Zugang | Phase |
|---|---|---|---|
| UN Comtrade | Bilaterale Handelsmengen (kg) und -werte (USD), monatlich/jährlich, HS 3901 | öffentlicher Preview-Endpunkt **ohne Key** (Key optional, siehe unten) | 1 |
| Eurostat Comext | EU-Handel, detaillierter, als Abgleich | öffentliche API/Bulk | 1 (optional) |
| Seewege/Distanzen | Distanz zwischen repräsentativen Häfen je Region | Python-Paket `searoute` | 1 |
| Brent-Ölpreis | Treiber für Rohstoff- und Bunkerkosten | FRED-CSV `DCOILBRENTEU` ohne Key (ADR-004) | 1 |
| Kapazitäten/Kosten | Regionale PE-Kapazität und Cash-Kosten | **Annahmen** aus öffentlichen Quellen, klar gekennzeichnet | 2 |

API-Details (Endpunkte, Limits, Parameter) vor der Implementierung in der aktuellen Doku prüfen.

**Comtrade-Zugang (entschieden in Phase 0, ADR-003):** Wir nutzen den öffentlichen Endpunkt `https://comtradeapi.un.org/public/v1/preview/C/{freq}/HS` ohne Registrierung. Grenzen: max. 500 Datensätze und **ein Jahr** pro Abfrage (Abfrage daher je Melder und Jahr; bei genau 500 Zeilen getrennt nach Import/Export), keine ISO-Codes in der Antwort (Zuordnung über die Comtrade-Referenztabellen), Folgeanfragen werden gedrosselt (HTTP 429, beobachtet am 2026-11-12). Der Ingest wartet daher zwischen Abfragen, wiederholt bei 429 mit Backoff und cacht jede Antwort im `raw`-Layer. Ist `COMTRADE_API_KEY` gesetzt, darf der Ingest später auf den Key-Endpunkt umschalten; erforderlich ist das nicht.

### Startumfang
- Jahre: 2019–2024 (2025 erst, wenn die Meldeabdeckung ausreicht; viele Länder melden mit 6–18 Monaten Verzug)
- Frequenz: zuerst jährlich, später monatlich
- Länder: 30 große Exporteure/Importeure in **10 Modellregionen** (NAM, SAM, EUR, CIS, MDE, AFR, IND, CHN, NEA, SEA) – Zuordnung und repräsentativer Hafen je Region in `config/regions.yaml`, Begründung in `docs/methodology.md`. Taiwan meldet nicht und erscheint in Comtrade als „Other Asia, nes“ (`S19` → `TWN`).
- Alle übrigen Länder fallen in eine Region **„Rest der Welt“ (`ROW`)**, damit keine Mengen verloren gehen.

## 3. Datenpipeline

### Layer
- **raw:** API-Antworten unverändert als Parquet, mit Abrufzeitpunkt
- **clean:** einheitliches Schema, Einheiten normiert (Tonnen, USD)
- **model:** Region-zu-Region-Matrizen, Inputs für das LP

### Clean-Schema (Minimum)
`year, month, reporter_iso3, partner_iso3, flow (import|export), hs_code, qty_t, value_usd, source, qty_estimated_by_source, is_imputed, imputation_method`

- `qty_estimated_by_source` übernimmt das Comtrade-Flag `isNetWgtEstimated` (Comtrade schätzt Gewichte teils selbst).
- Clean-Tabellen: `trade_reports` (eine Zeile je Meldung, Schema oben), `mirror` (Export- und Importmeldung je Relation nebeneinander), `bilateral_flows` (eine abgestimmte Menge je Jahr/Exporteur/Importeur).

- `month` ist bei Jahresdaten leer (null).
- Ausgefiltert werden: Re-Exporte/Re-Importe sowie Aggregat-Partner wie „World“ (Comtrade-Code 0).

### Qualitätsregeln
1. Einheitswerte (USD/t) berechnen; Ausreißer markieren: |log(Einheitswert) − Median| > 3 × MAD·1,4826, je Jahr und Flussrichtung (Schwelle in `config/pipeline.yaml`).
2. **Spiegelstatistik:** Export A→B vs. Import B←A vergleichen. Abweichung messen und dokumentieren. Primär über **Mengen** (t), da Importwerte CIF und Exportwerte FOB sind und sich systematisch um Fracht/Versicherung unterscheiden.
3. **Abgleich-Regel (MVP):** Importmeldungen bevorzugen (CIF, meist zuverlässiger), Export als Fallback; eine plausible Exportmeldung schlägt eine Importmeldung mit Ausreißer-Einheitswert. Mengen ohne Gewicht über Wert ÷ regionalen Median-Einheitswert (Region des Melders, Jahr, Flussrichtung; Fallback global) imputieren.
4. Jede Imputation setzt `is_imputed=True` und nennt die Methode.
5. Data-Quality-Report (Abdeckung, Abweichungen, Imputationsanteil) als Tabelle/Grafik.

## 4. Optimierungsmodell (Transport-LP)

### Mengen
- `R`: Regionen; `i ∈ R` Angebotsregion, `j ∈ R` Nachfrageregion

### Parameter
- `cap_i`: Produktionskapazität (t/Jahr) – Annahme
- `prod_cost_i`: Produktionskosten (USD/t) – Annahme, optional an Brent gekoppelt
- `dem_j`: Nachfrage (t/Jahr) = angenommene Produktion (`cap_j` × Auslastung) + Importe − Exporte (scheinbarer Verbrauch). Produktion ist nicht in Comtrade enthalten und daher eine gekennzeichnete Annahme (`source: assumption`).
- `dist_ij`: Seedistanz (nm)
- `freight_ij`: Frachtkosten (USD/t) = fix + variabel × Distanz (Parameter in Config)
- `tariff_ij`: Zollaufschlag in **USD/t**, Standard 0 (Prozentzölle bräuchten einen Preis und machen das Modell zirkulär)
- `penalty`: Strafkosten für ungedeckte Nachfrage (USD/t), deutlich über allen Versorgungskosten (Config)

### Entscheidungsvariablen
- `x_ij ≥ 0`: Menge von i nach j (t); `x_ii` = lokale Versorgung (Frachtkosten ≈ 0)
- `u_j ≥ 0`: ungedeckte Nachfrage in j (t). Hält das LP auch dann lösbar, wenn ein Szenario die Kapazität unter die Nachfrage drückt.

### Ziel
min Σ_ij (prod_cost_i + freight_ij + tariff_ij) · x_ij + Σ_j penalty · u_j

### Nebenbedingungen
- Kapazität: Σ_j x_ij ≤ cap_i  ∀ i
- Nachfrage: Σ_i x_ij + u_j ≥ dem_j  ∀ j

### Auswertung
- Optimale Ströme vs. beobachtete Ströme (Matrixvergleich, Kennzahlen z. B. Anteil korrekt erklärter Menge). Verglichen werden nur **interregionale** Ströme (i ≠ j): Handel innerhalb einer Region (z. B. DE→FR) verschwindet im Modell in `x_ii`.
- `u_j > 0` wird als Versorgungslücke ausgewiesen; der Schattenpreis ist dann durch `penalty` gedeckelt.
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
- Woher kommen plausible Kapazitäts- und Kostenannahmen je Region? Kandidaten: Investorenpräsentationen (SABIC, Dow, LyondellBasell, Borealis), IEA „The Future of Petrochemicals“, Plastics Europe, ACC. Bandbreiten statt Punktwerte, Quellen dokumentieren. Entscheidung in Phase 2.

### Entschieden
- LP-MVP: **jährlich** (Kapazitäten sind Jahresgrößen; Monatsdaten verrauscht durch Lager und Transitzeiten).
- Datenverarbeitung: **pandas** (siehe `docs/decisions.md`, ADR-002).
