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
- `uv run pytest --cov=ptf --cov-fail-under=85` grün; neue Logik hat eigene Tests mit nachrechenbaren Werten
- neue oder geänderte Tabellen stehen in `docs/data_dictionary.md` (der Datenkatalog-Test prüft das)
- neue Annahmen stehen in `config/` mit Quelle und in `docs/methodology.md`
- größere Entscheidungen als ADR in `docs/decisions.md`; `CHANGELOG.md` unter „Unreleased“ ergänzt

## Tech-Stack (verbindlich)

- Python 3.12, Paket- und Umgebungsverwaltung mit **uv** (`uv add`, `uv run`)
- Datenhaltung lokal: **Parquet** + **DuckDB** (Layer: `raw` → `clean` → `model`), angelehnt an ein Lakehouse
- Datenverarbeitung: **pandas** (entschieden, Begründung in `docs/decisions.md`, ADR-002)
- Optimierung: **Pyomo** mit dem freien Solver **HiGHS** (`highspy`)
- Visualisierung/App: **Dash** + Plotly
- Qualität: **pytest**, **ruff** (lint + format), **pre-commit**, Type Hints
- Konfiguration: `.env` + `pydantic-settings`; **niemals Secrets committen**
- Später: **Docker**, **docker compose**, **Apache Airflow**, GitHub Actions (CI)

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
├── config/
│   ├── regions.yaml          # Länder → Modellregionen
│   └── scenarios.yaml        # Szenario-Definitionen
├── data/                     # NICHT in Git (außer kleine Seed-/Fixture-Dateien)
│   ├── raw/
│   ├── clean/
│   └── model/
├── docs/
│   ├── decisions.md          # Architecture Decision Records, kurz
│   └── methodology.md        # Modellannahmen und Grenzen
├── notebooks/                # nur Exploration, keine Logik
├── src/ptf/
│   ├── config.py
│   ├── ingest/               # Comtrade, Eurostat, Distanzen, Ölpreis
│   ├── clean/                # Bereinigung, Spiegelstatistik, Imputation
│   ├── model/                # LP, Kalibrierung, Kostenkurven
│   ├── scenarios/
│   ├── forecast/             # optional, Phase 4
│   └── app/                  # Dash
├── tests/
│   └── fixtures/
├── dags/                     # Airflow, Phase 5
└── docker/
```

## Regeln

- Code, Bezeichner, Docstrings und Commit-Messages auf **Englisch**. Erklärungen an mich auf **Deutsch**.
- Geschäftslogik gehört in `src/ptf/`, nicht in Notebooks oder die Dash-App.
- Jede Modellannahme (Frachtkostensatz, Kapazitäten, Regionenzuordnung) steht in Config oder Datei, nicht hart im Code, und ist in `docs/methodology.md` dokumentiert.
- Wenn Daten fehlen oder nur als Annahme vorliegen: klar kennzeichnen (`source: assumption`), nicht stillschweigend erfinden.
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
```
