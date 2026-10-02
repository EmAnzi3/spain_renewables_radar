# Spain Renewables Radar

Radar separato per monitorare la pipeline spagnola di progetti **fotovoltaici, eolici, BESS e ibridi** usando, in questa fase, **solo fonti ufficiali e gratuite**.

## Obiettivo

Trasformare i bollettini ufficiali spagnoli in un flusso simile a `pv_agent_mvp`:

**fonti ufficiali → eventi amministrativi → progetto unico → lifecycle → report modifiche → dashboard**.

Nessun aggregatore commerciale è usato come sorgente o dipendenza.

## MVP iniziale

Implementato:
- collector BOE giornaliero;
- filtro FV/eolico/storage/ibridazione;
- parsing preliminare di tecnologia, MW, progetto, provincia e Comunidad Autónoma;
- lifecycle amministrativo;
- SQLite locale;
- deduplica evento/progetto;
- storico eventi;
- report CSV/HTML delle variazioni;
- dashboard statica GitHub Pages;
- BAT Windows;
- registry BOE + 17 bollettini autonomici;
- test automatici del parser/collector.

Da implementare:
- collector regionali;
- enrichment REE accesso/connessione;
- enrichment EPC/BoP;
- geocodifica/mappa provinciale;
- backfill storico;
- scoring commerciale.

## Fonti gratuite target

Primary:
- BOE;
- BOJA, BOA, BOPA, BOIB, BOC Canarias, BOCANT, DOCM, BOCYL, DOGC, DOGV, DOE, DOG, BOCM, BORM, BON, BOPV, BOR.

Enrichment:
- Red Eléctrica (REE): accesso/connessione;
- MITECO / registro impianti;
- comunicati pubblici di EPC, developer, turbine/module supplier solo come fonti secondarie esplicite.

## Avvio Windows

```bat
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
aggiorna_radar_spagna.bat
```

Backfill manuale 30 giorni:

```bat
.\.venv\Scripts\python.exe -m app.run_pipeline --days 30
```

## Output

- database: `data/spain_renewables.sqlite`
- report: `reports/change_reports/changes_latest.html`
- CSV: `reports/change_reports/changes_latest.csv`
- dataset dashboard: `docs/data.json`
- dashboard: `docs/index.html`

## Regola chiave

Uno stesso impianto mantiene **una sola entità progetto** e accumula eventi amministrativi successivi. Non si crea un nuovo progetto a ogni pubblicazione.
