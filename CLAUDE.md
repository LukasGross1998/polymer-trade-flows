# CLAUDE.md – Projektkontext für Claude Code

## Worum es geht

**Polymer Trade Flow & Disruption Simulator**: ein Portfolio-Projekt, das globale Handelsströme von Polyethylen (HS 3901) modelliert, mit einem Transport-LP erklärt und Störungsszenarien (z. B. Sperrung Rotes Meer/Suez, Panamakanal, Zölle, Werksausfälle) simuliert. Ergebnis ist eine interaktive Dash-App.

Zweck: Bewerbung als **Senior Data Scientist (Commodity Markets / Chemicals)**. Das Repo muss zeigen:
- Umgang mit unvollständigen, widersprüchlichen Handelsdaten (Bereinigung, Imputation, Spiegelstatistiken)
- Mathematische Optimierung (lineare Programmierung) mit Marktinterpretation (Schattenpreise)
- Szenario-Modellierung und Kostenkurven
- Produktionsreife Software: Modularisierung, Tests, Git, Docker, Airflow
- Spec-Driven Development

Die fachliche Spezifikation steht in `SPEC.md`. **Lies sie vor jeder neuen Phase.**

## Über mich (den Entwickler)

- Erfahrener Software Engineer (ERP, Infor LN), AWS Solutions Architect Associate.
- **Neu in Data Science, Python-Data-Stack und Optimierung.**
- Erkläre daher bei neuen Konzepten (LP-Formulierung, Duals, Imputation, Pyomo, Dash-Callbacks) kurz das *Warum*, bevor du Code schreibst. Keine Lehrbuch-Romane – 3–6 Sätze reichen.
- Ich muss jede Zeile im Interview erklären können. Lieber einfacher, verständlicher Code als clevere Einzeiler.

## Arbeitsweise

1. **Spec first.** Vor jeder Phase: relevante Abschnitte in `SPEC.md` prüfen, Lücken oder Widersprüche benennen, ggf. Änderung an `SPEC.md` vorschlagen. Erst nach meiner Zustimmung implementieren.
2. **Plan, dann bauen.** Für jede Phase zuerst einen kurzen Plan (Dateien, Funktionen, Tests) vorlegen und auf mein OK warten.
3. **Klein anfangen.** Erst die einfachste funktionierende Version (MVP), dann iterieren. Keine vorauseilende Abstraktion.
4. **Kleine Commits** mit aussagekräftigen Messages (Conventional Commits: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`). Nach jedem logischen Schritt committen.
5. **Tests zuerst oder parallel**, besonders für Datenbereinigung und Modell-Constraints.
6. **Am Ende jeder Phase:** Tests laufen grün, `ruff` ist sauber, README/`docs/decisions.md` aktualisiert, kurze Zusammenfassung an mich mit dem, was ich im Interview darüber sagen könnte.
7. **Unsicher bei externen APIs?** Aktuelle Doku prüfen statt raten. Endpunkte, Parameter und Limits ändern sich.
8. **Spec → Branch → PR → Review → Merge** (ADR-010). Jede Änderung, die mehr als ein Tippfehler ist:
   - kurze Feature-Spec in `specs/NNN-name.md` nach `specs/TEMPLATE.md` (Ziel, Akzeptanzkriterien, Nicht-Ziele); `SPEC.md` bleibt der Gesamtüberblick
   - eigener Branch (`feat/…`, `fix/…`, `chore/…`, `docs/…`), nie direkt auf `main` committen
   - Akzeptanzkriterien werden zu Tests, bevor oder während der Code entsteht
   - PR mit der Checkliste aus `.github/pull_request_template.md`; CI muss grün sein; Review durch mich (oder `/code-review`) vor dem Merge
   - nach jeder Phase: Versions-Tag (`vMAJOR.MINOR.PATCH`) und Eintrag in `CHANGELOG.md`

## Definition of Done (gilt für jeden PR)

- `uv run ruff check .` und `uv run ruff format --check .` sauber
- `uv run mypy` ohne Fehler (strict, ADR-010)
- `uv run lint-imports` hält die Paketregeln ein (ADR-012)
- `uv run pytest --cov=ptf --cov-fail-under=85` grün; neue Logik hat eigene Tests mit nachrechenbaren Werten
- neue oder geänderte Tabellen stehen in `docs/data_dictionary.md` (Dateien) bzw. in den dbt-YAML-Dateien (Warehouse); der Datenkatalog-Test prüft beides
- Warehouse-Modelle haben dbt-Tests (Schlüssel, Beziehungen, Wertebereiche)
- neue Werte stehen in `config/` mit Quelle, URL und Lesedatum (oder als Einstellung) und in `docs/value_register.md` (ADR-016)
- größere Entscheidungen als ADR in `docs/decisions.md`; `CHANGELOG.md` unter „Unreleased“ ergänzt

## Tech-Stack (verbindlich)

- Python 3.12, Paket- und Umgebungsverwaltung mit **uv** (`uv add`, `uv run`)
- Datenhaltung lokal: **Parquet** + **DuckDB** (Layer: `raw` → `clean` → `model`), angelehnt an ein Lakehouse; Transformationen in SQL mit **dbt** (`dbt/`, ADR-011)
- Datenverarbeitung: **pandas** (entschieden, Begründung in `docs/decisions.md`, ADR-002)
- Optimierung: **Pyomo** mit dem freien Solver **HiGHS** (`highspy`)
- Visualisierung/App: **Dash** + Plotly
- Qualität: **pytest**, **ruff** (lint + format), **pre-commit**, Type Hints
- Konfiguration: `.env` + `pydantic-settings`; **niemals Secrets committen**
- Container: **Docker** + **docker compose** (ADR-013); CI mit GitHub Actions; später **Apache Airflow**

## Projektstruktur (Zielbild)

```
polymer-trade-flows/
├── CLAUDE.md
├── SPEC.md
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── config/                   # eine Datei je Fachgebiet (ADR-012)
│   ├── regions.yaml          # Länder → Modellregionen (geteilt, core)
│   ├── trade.yaml, shipping.yaml, markets.yaml, model.yaml
│   ├── comtrade.yaml         # legacy
│   └── scenarios.yaml        # Szenario-Definitionen (geplant)
├── data/                     # NICHT in Git (außer kleine Seed-/Fixture-Dateien)
│   ├── raw/
│   ├── clean/
│   └── model/
├── docs/
│   ├── decisions.md          # Architecture Decision Records, kurz
│   └── methodology.md        # Modellannahmen und Grenzen
├── notebooks/                # nur Exploration, keine Logik
├── dbt/                      # SQL-Modelle, nach Fachgebiet (ADR-011)
├── src/ptf/                  # nach Fachgebiet geschnitten (ADR-012)
│   ├── core/                 # Settings, HTTP, Warehouse, Regionen – kennt kein Fachgebiet
│   ├── trade/                # BACI, Referenztabellen, Datenqualitäts-Report
│   ├── shipping/             # PortWatch, Monitor-Kennzahlen, Hafennetz
│   ├── markets/              # FRED, GSCPI, Indikatoren
│   ├── model/                # Distanzen, LP, später Kalibrierung, Kostenkurven
│   ├── scenarios/            # geplant
│   ├── forecast/             # optional, Phase 4
│   ├── legacy/comtrade/      # abgelöste Comtrade-Gegenprobe
│   ├── app/                  # Dash
│   └── cli.py                # `uv run ptf <schritt>`
├── tests/
│   └── fixtures/
├── dags/                     # Airflow, Phase 5
└── docker/                   # Rauchprobe des Images; Dockerfile und compose.yaml im Wurzelordner
```

## Regeln

- Code, Bezeichner, Docstrings und Commit-Messages auf **Englisch**. Erklärungen an mich auf **Deutsch**.
- Geschäftslogik gehört in `src/ptf/`, nicht in Notebooks oder die Dash-App.
- Fachgebiete importieren nur `core`, nie einander; Daten eines anderen Fachgebiets kommen aus dem Warehouse (`uv run lint-imports` prüft das, ADR-012). Jedes Fachgebiet hat `config.py` und `steps.py`.
- Jeder Wert (Frachtsatz, Kapazität, Regionenzuordnung) steht in Config oder Datei, nicht hart im Code, mit Quelle oder als Einstellung, und ist in `docs/methodology.md` und `docs/value_register.md` dokumentiert.
- Nur Werte, die eine Datenquelle bestätigt, ohne Ausnahme (ADR-016). Fehlt eine Quelle, zeigt die App „n/a“ statt einer Schätzung; Einstellungen des Nutzers (Schwellen, Zeitfenster) sind keine Daten und als solche gekennzeichnet.
- Rohdaten werden nie überschrieben; Transformationen sind reproduzierbar.
- Keine riesigen Datenmengen ziehen: mit wenigen Ländern/Jahren starten, API-Limits respektieren, Ergebnisse cachen.

## Häufige Befehle

```bash
uv sync                      # Abhängigkeiten installieren
uv run pytest                # Tests
uv run ruff check . --fix    # Lint
uv run ruff format .         # Format
uv run mypy                  # Typprüfung (strict)
uv run pytest -m "not slow"  # schnelle Tests ohne echte Seerouten
uv run pytest --cov=ptf      # Tests mit Abdeckung (CI verlangt 85 %)
uv run python -m ptf.app     # Dash-App starten (ab Phase 3)
uv run ptf clean             # BACI entpacken + dbt build (Warehouse)
uv run lint-imports          # Abhängigkeitsregeln der Pakete (ADR-012)
docker compose up -d app     # App im Container (ADR-013), http://localhost:8050
docker compose run --rm pipeline model   # Pipeline-Schritt im Container
cd dbt && uv run dbt build --profiles-dir .   # nur dbt, aus dem Ordner dbt/
```
