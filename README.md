# Spain Renewables Radar

Radar separato per monitorare la pipeline spagnola di progetti **fotovoltaici, eolici, BESS e ibridi** usando, in questa fase, **solo fonti ufficiali e gratuite**.

## Architettura

**bollettini ufficiali → eventi amministrativi → progetto unico → lifecycle → enrichment REE/MITECO → controlli qualità → report/dashboard**

Nessun aggregatore commerciale è usato come sorgente o dipendenza.

## Fonti operative

Collector ufficiali attualmente implementati:

- **BOE** — Boletín Oficial del Estado;
- **BOCYL** — Castilla y León;
- **BOA** — Aragón;
- **BOJA** — Andalucía;
- **DOCM** — Castilla-La Mancha;
- **DOE** — Extremadura;
- **BORM** — Región de Murcia, acquisito dal dataset ufficiale Open Data degli indici BORM;
- **BOCM** — Comunidad de Madrid, acquisito dalla fonte ufficiale per data/XML.

Enrichment gratuito implementato:

- **REE** — snapshot di capacità/accesso per nodo, usato come contesto di rete e non come falsa conferma del singolo progetto;
- **MITECO / Registro administrativo de instalaciones de producción** — snapshot del registro impianti e matching conservativo per nome progetto + CCAA.

Il registry `config/sources.json` contiene anche gli altri bollettini autonomici, marcati `implemented=false` finché non esiste un collector realmente validato.

## Stato validato

Backfill ufficiale di 30 giorni, run GitHub Actions **37114835344**:

- **107 progetti**;
- **129 eventi amministrativi**;
- quality gate: **0 ERROR, 1 WARN, 44 INFO**;
- BOE 42 eventi;
- BOCYL 15;
- BOA 24;
- BOJA 7;
- DOCM 17;
- DOE 8;
- BORM 11;
- BOCM 5;
- REE: **931 nodi** nello snapshot 2026-10-01;
- MITECO: **71.727 impianti** nello snapshot 2026-10-03, con **8 matching esatti** conservativi;
- 2 warning source/day BOA dovuti a errori di rete transitori; il workflow resta verde e il collector ha retry.

Il radar conserva un progetto come entità unica e accumula eventi successivi. Non crea un nuovo progetto a ogni pubblicazione.

## Lifecycle

Eventi riconosciuti:

`PUBLIC_INFO`, `DIA`, `PRIOR_AUTH`, `CONSTRUCTION_AUTH`, `PUBLIC_UTILITY`, `EXPROPRIATION`, `MODIFICATION`, `WITHDRAWN`, `DENIED`.

Stati commerciali derivati:

`EARLY`, `PERMITTING`, `AUTHORIZED`, `PRECONSTRUCTION`, `BLOCKED`.

## Avvio Windows

```bat
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
aggiorna_radar_spagna.bat
```

Backfill manuale:

```bat
.\.venv\Scripts\python.exe -m app.run_pipeline --days 30
```

## Output

- DB: `data/spain_renewables.sqlite`
- variazioni: `reports/change_reports/changes_latest.html`
- coverage sorgenti: `reports/coverage_latest.html`
- quality gate: `reports/quality_issues_latest.html`
- REE: `reports/ree_capacity_latest.csv`
- MITECO: `reports/miteco_registry_latest.csv`
- matching MITECO: `reports/miteco_exact_matches_latest.csv`
- dashboard: `docs/index.html`

## Regole

- fonte ufficiale e URL originario sempre preservati;
- meglio un campo vuoto che un dato inventato;
- owner/promotore ed EPC sono entità diverse;
- dati REE aggregati per nodo/CCAA non equivalgono automaticamente alla conferma di un progetto;
- i flag qualità **non correggono automaticamente** i dati: isolano i record da verificare;
- una pubblicazione che raggruppa più progetti senza nomi individuali resta senza nome e viene classificata come WARN, non viene inventata una denominazione.
