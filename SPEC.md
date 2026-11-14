# SPEC: Polymer Trade Flow & Disruption Simulator

Status: v0.8 (Entwurf) – wird in jeder Phase verfeinert.

Änderungen v0.8: Handelsdaten aus CEPII BACI statt eigenem Comtrade-Abruf (ADR-009); Comtrade bleibt als Gegenprobe; Clean-Tabellen `trade_hs6`, `bilateral_flows`, `comtrade_flows`.

Änderungen v0.7: Tab „Trade flows“ (Hafennetz, Ladungsmix je Land optional), Abschnitt 7b.

Änderungen v0.6: Dashboard mit vier Tabs (Überblick, Meerengen, Häfen, Energie & Fracht), Abschnitt 7b; Szenario-Modelle zurückgestellt.

Änderungen v0.5: Schifffahrts-Monitor (IMF PortWatch) als erster Tab der Dash-App, Abschnitt 7a.

Änderungen v0.4 (Phase 2): Regionen mit `reporters` und `members` (alle Länder einer Region), `ROW` nicht im LP, Basisjahr 2023, Definition „erklärter Anteil“, Vorzeichen der Duals, Annahmen in `config/model.yaml`.

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
| **CEPII BACI** | Abgeglichener bilateraler Handel je HS6-Produkt (Wert FOB in Tsd. USD, Menge in t), jährlich, alle Länder | Zip-Datei V202601, HS17, ~800 MB, frei (Etalab 2.0), ADR-009 | 1 |
| UN Comtrade (nur Gegenprobe) | Eigene Meldungsdaten aus Phase 1 | öffentlicher Preview-Endpunkt ohne Key, Tageskontingent | 1 |
| Eurostat Comext | EU-Handel, detaillierter, als Abgleich | öffentliche API/Bulk | 1 (optional) |
| Seewege/Distanzen | Distanz zwischen repräsentativen Häfen je Region | Python-Paket `searoute` | 1 |
| Brent-Ölpreis | Treiber für Rohstoff- und Bunkerkosten | FRED-CSV `DCOILBRENTEU` ohne Key (ADR-004) | 1 |
| Kapazitäten/Kosten | Regionale PE-Kapazität und Cash-Kosten | **Annahmen** aus öffentlichen Quellen, klar gekennzeichnet | 2 |

API-Details (Endpunkte, Limits, Parameter) vor der Implementierung in der aktuellen Doku prüfen.

**Comtrade-Zugang (Phase 0, ADR-003; seit ADR-009 nur noch Gegenprobe):** Wir nutzen den öffentlichen Endpunkt `https://comtradeapi.un.org/public/v1/preview/C/{freq}/HS` ohne Registrierung. Grenzen: max. 500 Datensätze und **ein Jahr** pro Abfrage (Abfrage daher je Melder und Jahr; bei genau 500 Zeilen getrennt nach Import/Export), keine ISO-Codes in der Antwort (Zuordnung über die Comtrade-Referenztabellen), Folgeanfragen werden gedrosselt (HTTP 429, beobachtet am 2026-11-12). Der Ingest wartet daher zwischen Abfragen, wiederholt bei 429 mit Backoff und cacht jede Antwort im `raw`-Layer. Ist `COMTRADE_API_KEY` gesetzt, darf der Ingest später auf den Key-Endpunkt umschalten; erforderlich ist das nicht.

### Startumfang
- Jahre: 2019–2024 (2025 erst, wenn die Meldeabdeckung ausreicht; viele Länder melden mit 6–18 Monaten Verzug)
- Frequenz: zuerst jährlich, später monatlich
- Länder: 30 große Exporteure/Importeure in **10 Modellregionen** (NAM, SAM, EUR, CIS, MDE, AFR, IND, CHN, NEA, SEA) – Zuordnung und repräsentativer Hafen je Region in `config/regions.yaml`, Begründung in `docs/methodology.md`. Taiwan meldet nicht und erscheint in Comtrade als „Other Asia, nes“ (`S19` → `TWN`).
- Jede Region hat `reporters` (bei Comtrade abgefragt) und `members` (alle übrigen Länder der Region, nicht abgefragt). Nur nicht zugeordnete Länder (v. a. Ozeanien) fallen in **„Rest der Welt“ (`ROW`)**; `ROW` ist nicht Teil des LP, sein Handel zählt aber in Importe/Exporte der Modellregionen.

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
1. Einheitswerte (USD/t) berechnen; Ausreißer markieren: |log(Einheitswert) − Median| > 3 × MAD·1,4826, je Jahr und Flussrichtung (Schwelle in `config/comtrade.yaml`).
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
- Basisjahr 2023 (`config/model.yaml`).
- Optimale Ströme vs. beobachtete Ströme (Matrixvergleich, Kennzahlen). **Erklärter Anteil** = Σ min(Modell, Realität) / Σ Realität je Route. Verglichen werden nur **interregionale** Ströme (i ≠ j): Handel innerhalb einer Region (z. B. DE→FR) verschwindet im Modell in `x_ii`.
- `u_j > 0` wird als Versorgungslücke ausgewiesen; der Schattenpreis ist dann durch `penalty` gedeckelt.
- **Duals der Nachfrage-Constraints** = marginale Versorgungskosten je Region → als implizite regionale Preise interpretieren
- Duals der Kapazitäts-Constraints = Knappheitsrente (Dual ≤ 0 in der Minimierung, ausgewiesen als positiver Betrag `rent_usd_t`)

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
0. **Schifffahrts-Monitor:** siehe Abschnitt 7a (zuerst gebaut)
1. **Datenqualität:** Abdeckung, Spiegelabweichungen, Imputationsanteil
2. **Beobachtete Ströme:** Weltkarte mit Strompfeilen (Plotly `scattergeo`), Filter Jahr/Region
3. **Modell vs. Realität:** Vergleichsmatrix/Heatmap, Kennzahlen
4. **Szenarien:** Szenario wählen, Parameter per Slider (Frachtsatz, Zoll, Kapazität), Vorher/Nachher-Karte, Tabelle Δ Schattenpreise, Kostenkurve

### Akzeptanzkriterien
- App startet mit einem Befehl lokal und in Docker
- Szenario-Neuberechnung < 5 s
- Keine Geschäftslogik in Callbacks (nur Aufrufe von `src/ptf/...`)

## 7a. Schifffahrts-Monitor (IMF PortWatch)

**Ziel:** Störungen an maritimen Meerengen früh erkennen und einordnen: Wie viel Verkehr gibt es aktuell im Vergleich zum Normalniveau, und wohin weicht er aus?

**Daten:** IMF PortWatch, ArcGIS-API ohne Key. `Daily_Chokepoints_Data`: Durchfahrten je Tag, Meerenge und Schiffstyp (Container, Massengut, Stückgut, RoRo, Tanker) plus Tragfähigkeit, ab 2019-01-01, 28 Meerengen. `PortWatch_chokepoints_database`: Stammdaten (Name, Lage). Max. 1.000 Zeilen pro Abfrage → seitenweise; inkrementell nur Tage nach dem letzten Stand. **Keine Echtzeit:** Tageswerte mit einigen Tagen Verzug, etwa wöchentlich aktualisiert.

**Kennzahlen** (Logik in `src/ptf/shipping/`, Parameter in `config/shipping.yaml`):
- 7-Tage-Durchschnitt der Durchfahrten je Meerenge und Schiffstyp
- Normalniveau: Mittel derselben Kalenderwoche im Basiszeitraum 2019–2023 (vor der Rotes-Meer-Krise)
- Abweichung vom Normalniveau in % und Störungs-Flag unterhalb einer Schwelle (Start: 70 % des Normalniveaus)
- Umleitungsquote Rotes Meer: Containerschiffe am Kap / (Kap + Bab el-Mandeb), 7-Tage-Basis

**Ansichten:** Weltkarte aller Meerengen (Größe = aktuelles Volumen, Farbe = Abweichung), Kennzahl-Kacheln, Zeitreihe mit Band für das Normalniveau (Auswahl Meerenge, Schiffstyp, Zeitraum), Grafik Rotes-Meer-Umleitung, Datenstand mit Quelle, Knopf „Daten aktualisieren“.

**Akzeptanzkriterien:** Start mit `uv run python -m ptf.app`; Reaktion auf Auswahl < 1 s; Aktualisierung lädt nur neue Tage; Kennzahlen getestet; keine Logik in Callbacks.

## 7b. Dashboard: Häfen, Ereignisse, Energie & Fracht

**Tabs:** Überblick (Lagebild), Meerengen (7a), Häfen, Trade flows, Energie & Fracht.

**Trade flows:** Hafen-zu-Hafen-Netz von PortWatch (fester Stand Mai 2025, alle Schiffstypen, Kapazität statt Ladung; Standard: Langstrecken ab 5 Tagen zwischen Ländern) und – optional, weil der erste Abruf 20–25 min dauert – Importe/Exporte je Land nach Schiffstyp als Stellvertreter für die Ladungsart. Ströme nach Ware zwischen Ländern (BACI) folgen später.

**Daten** (alle frei, ohne Key; Details `docs/methodology.md` Abschnitt 5):
- PortWatch `Daily_Ports_Data` für die Häfen in `config/shipping.yaml` (Anläufe, geschätzte Import-/Exportmengen), gleiche Kennzahlen wie bei den Meerengen
- PortWatch `portwatch_disruptions_database` (Ereignisse mit Alarmstufe)
- FRED-Reihen in `config/markets.yaml` (Öl, Gas, Frachtindex als Näherung, Harzpreisindex, Wechselkurse) und NY Fed GSCPI
- Containerraten (WCI, FBX, SCFI): nicht frei verfügbar, daher nicht enthalten

**Darstellung:** Reihen mit unterschiedlichen Einheiten indexiert (Start = 100) statt zweiter y-Achse; Schlüsselereignisse als Markierung in allen Zeitreihen; Statusfarben nur mit Symbol und Text.

**Akzeptanzkriterien:** Jeder Tab reagiert in < 1 s; fehlende Daten führen zu einem Hinweis statt zu einem Fehler; keine Logik in Callbacks.

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

## 10. Stand & nächste Schritte (Stand 2026-11-13)

### Stand
- **Phase 1 (Daten):** fertig. Handelsdaten aus **CEPII BACI** (ADR-009): 68–70 Mt Welthandel pro Jahr, alle Länder, Aufteilung nach PE-Typen. Eigener Comtrade-Abgleich bleibt als Gegenprobe (`ptf comtrade`); er liegt bei etwa der Hälfte der Relationen innerhalb ±10 % von BACI.
- **Phase 2 (LP):** gerechnet mit BACI für 2023 (`docs/model_results.md`): erklärt 42 % des interregionalen Handels (44 Mt), Korrelation 0,57; Randlösung (Europa produziert 0 t). Kostenannahmen sind die schwächste Stelle.
- **Dashboard (Teil von Phase 3):** zwei Bereiche – *Buying* (Situation, Prices & drivers, Sourcing, Landed cost; Spec 006/007, Sortenfilter Spec 008) und *Markets & logistics* (World trade by class, Chokepoints mit Schiffsklassen, Ports, Trade flows). Start: `uv run ptf portwatch`, `... market`, dann `uv run python -m ptf.app`.
- **Länderhandel nach Ladungsart** (PortWatch, ~560.000 Zeilen) ist abgeschaltet (`download_country_trade: false` in `config/shipping.yaml`); erster Abruf 20–25 min.

### Nächste Schritte (Vorschlag, in dieser Reihenfolge)
Architektur zuerst (ADR-010), jeder Schritt als eigene Spec in `specs/` und eigener PR:
1. ~~Arbeitsweise und Qualitätsschranken~~ (Spec 001, erledigt).
2. ~~**Datenmodell und Transformationen**~~ (ADR-011: dbt auf DuckDB): Handelsdaten (Spec 002), PortWatch und Marktdaten, App liest aus den Marts (Spec 003) – erledigt.
3. ~~**Paketstruktur nach Fachgebiet**~~ (ADR-012, Spec 004): `core`, `trade`, `shipping`, `markets`, `model`, `legacy`, `app`; CLI `uv run ptf <schritt>`; Regeln per import-linter – erledigt.
4. ~~**Docker**~~ (ADR-013, Spec 005): Image mehrstufig mit uv, compose mit `app` und `pipeline`, Rauchprobe in der CI – erledigt.
5. **Airflow:** zurückgestellt (2026-11-13), eventuell später gehostet statt lokal. Minimalentwurf: `airflow standalone` mit SQLite, Tasks starten das `ptf`-Image (DockerOperator), DAG Schifffahrt/Märkte täglich, Handel/Modell manuell.
6. **Betrieb:** Laufprotokoll, Frischeprüfungen, Prüfsummen.

Aktueller Fokus: **Einkäufer-Dashboard** (Spec 006: Lagebild, Preise & Treiber, Bezugsquellen mit Meerengen-Abhängigkeit – erledigt; Spec 007 Landed-Cost-Rechner – erledigt; Spec 008 Aufschlüsselung nach Klassen, Spec 009 Seewetter/WITS-Zölle/Seekarten, Spec 010 Bestellplaner – erledigt; als Nächstes Spec 011 Tagespreis LLDPE Dalian (AKShare), UNCTAD-Seehandel nach Ladungsart prüfen, Eurostat-Monatsimporte).

Danach fachlich:
7. **Kalibrierung:** Mindestauslastung je Region im LP; Kapazitäts- und Kostenannahmen gegen die BACI-Bilanz prüfen (z. B. Nachfrage Nahost nur 4,2 Mt, Nordostasien 3,5 Mt).
8. **Szenarien** (Abschnitt 5); Design steht: `red_sea_closed` (Passagen `babalmandab`, `suez` in searoute gesperrt), `red_sea_closed_high_freight` (zusätzlich variabler Frachtsatz ×2,5), `hormuz_closed` (Exportlimit Nahost 15 % der Kapazität; Jebel Ali liegt im Golf), `red_sea_and_hormuz`. Achtung: searoute liefert für blockierte Routen Distanz **0** statt Fehler – abfangen.
9. Kostenkurve und Szenario-Tab; Warenströme nach Ware aus der BACI-Zip; später Phase 4 (Prognose).

### Offene Fragen
- Kapazitäten außerhalb NAM/MDE/EUR/CHN und alle Cash-Kosten sind Größenordnungen; Quellen je Region noch einzeln prüfen.
- Yanbu (Saudi-Arabien, Rotes Meer): PortWatch meldet seit August 2026 fast keine Hafenanläufe mehr (Nullwerte, keine fehlenden Zeilen) – Hafen ruht oder Schiffe nicht per AIS sichtbar?
- Hafennetz (PortWatch) ist ein fester Stand vom Mai 2025, also vor der Hormus-Störung.

### Entschieden
- LP-MVP: **jährlich** (Kapazitäten sind Jahresgrößen; Monatsdaten verrauscht durch Lager und Transitzeiten).
- Datenverarbeitung: **pandas** (siehe `docs/decisions.md`, ADR-002).
- Weitere Entscheidungen: `docs/decisions.md` (ADR-003 bis ADR-008).
