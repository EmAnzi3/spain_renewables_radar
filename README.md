# Spain Renewables Radar

Radar per monitorare la pipeline spagnola di progetti **fotovoltaici, eolici, BESS e ibridi** usando **solo fonti ufficiali e gratuite**.

## Architettura

**bollettini ufficiali → eventi amministrativi → progetto unico → lifecycle → enrichment INE/REE/MITECO → scoring commerciale → controlli qualità → report/dashboard**

Nessun aggregatore commerciale è usato come sorgente o dipendenza.

## Fonti operative

Collector ufficiali implementati:

- **BOE** — Boletín Oficial del Estado;
- **BOCYL** — Castilla y León;
- **BOA** — Aragón;
- **BOJA** — Andalucía;
- **DOCM** — Castilla-La Mancha;
- **DOE** — Extremadura;
- **BORM** — Región de Murcia, tramite dataset ufficiale Open Data degli indici BORM;
- **BOCM** — Comunidad de Madrid, tramite fonte ufficiale per data/XML.

Enrichment gratuiti implementati:

- **INE** — catalogo ufficiale dei comuni per enrichment deterministico comune → provincia/CCAA;
- **REE** — snapshot di capacità/accesso per nodo, usato come contesto di rete e non come falsa conferma del singolo progetto;
- **MITECO / Registro administrativo de instalaciones de producción** — snapshot del registro impianti e matching conservativo per nome progetto + CCAA.

Il registry config/sources.json contiene anche gli altri bollettini autonomici, marcati implemented=false finché non esiste un collector realmente validato.

## Stato validato

Backfill ufficiale di 30 giorni, GitHub Actions **37134192228 — SUCCESS**:

- **106 progetti**;
- **128 eventi amministrativi**;
- source/day errors: **0**;
- quality gate: **0 ERROR, 1 WARN, 40 INFO**;
- BOE 41 eventi;
- BOCYL 15;
- BOA 24;
- BOJA 7;
- DOCM 17;
- DOE 8;
- BORM 11;
- BOCM 5;
- REE: **931 nodi** nello snapshot 2026-10-01;
- MITECO: **71.727 impianti** nello snapshot 2026-10-03, con **8 matching esatti** conservativi;
- missing: nome 1, MW 25, provincia singola 1, expediente 14.

Il solo progetto senza provincia singola è un caso multi-provincia esplicitamente riconosciuto. Non viene inventata una provincia unica.

## Lifecycle

Eventi riconosciuti:

PUBLIC_INFO, DIA, PRIOR_AUTH, CONSTRUCTION_AUTH, PUBLIC_UTILITY, EXPROPRIATION, MODIFICATION, WITHDRAWN, DENIED.

Stati derivati:

EARLY, PERMITTING, AUTHORIZED, PRECONSTRUCTION, BLOCKED.

## Scoring commerciale

Lo scoring è un layer separato dal lifecycle e non modifica il dato amministrativo.

Il dashboard esporta:

- commercial_score;
- commercial_priority;
- componenti dello score;
- recency;
- stato EPC, oggi EPC_UNKNOWN finché l'enrichment EPC non viene implementato.

## EPC / BoP

È implementato un layer conservativo di evidenze EPC/BoP sui documenti ufficiali già raccolti.

Stati:

- EPC_CONFIRMED
- EPC_CANDIDATE
- EPC_UNKNOWN

Il promotore non viene mai assunto come EPC. Sul backfill certificato corrente le fonti amministrative non contengono evidenze EPC/BoP sufficientemente esplicite: i 106 progetti restano quindi EPC_UNKNOWN.

Output dedicati:

- reports/epc_bop_evidence_latest.csv
- reports/epc_bop_evidence_latest.html

La prossima estensione userà comunicati EPC/developer/supplier, gare e documenti pubblici; eventuale stampa specializzata resterà un lead da confermare.

## Vista provinciale

La vista provinciale separa sempre:

- MW identificati;
- progetti senza MW.

Include conteggi per FV, eolico, BESS/ibrido e per stato EARLY, PERMITTING, AUTHORIZED, PRECONSTRUCTION e BLOCKED.

## Avvio Windows

~~~bat
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
aggiorna_radar_spagna.bat
~~~

Backfill manuale:

~~~bat
.\.venv\Scripts\python.exe -m app.run_pipeline --days 30
~~~

## Output

- DB: data/spain_renewables.sqlite
- variazioni: reports/change_reports/changes_latest.html
- coverage sorgenti: reports/coverage_latest.html
- quality gate: reports/quality_issues_latest.html
- EPC/BoP: reports/epc_bop_evidence_latest.html
- vista provinciale: reports/province_view_latest.html
- vista provinciale CSV: reports/province_view_latest.csv
- REE: reports/ree_capacity_latest.csv
- MITECO: reports/miteco_registry_latest.csv
- matching MITECO: reports/miteco_exact_matches_latest.csv
- dashboard: docs/index.html

## Regole

- fonte ufficiale e URL originario sempre preservati;
- meglio un campo vuoto che un dato inventato;
- owner/promotore ed EPC sono entità diverse;
- lifecycle e score commerciale restano separati;
- dati REE aggregati per nodo/CCAA non equivalgono automaticamente alla conferma di un progetto;
- i flag qualità non correggono automaticamente i dati;
- una pubblicazione che raggruppa più progetti senza nomi individuali resta senza nome;
- un progetto multi-provincia non viene forzato su una singola provincia.
