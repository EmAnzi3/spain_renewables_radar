# Spain Renewables Radar

Radar per progetti **fotovoltaici, eolici, BESS e ibridi** in Spagna, da fonti **ufficiali e gratuite**. Nessun aggregatore commerciale.

## Architettura

Fonti ufficiali → eventi amministrativi → progetto unico → lifecycle → enrichment INE/REE/MITECO → scoring separato → quality gate → report/dashboard.

## Stato certificato

**[Run 37220893072 — SUCCESS](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37220893072)**, codice funzionale `f4a88a6fe7a8706b5e30a52d168b93e060beaaeb`, finestra **4 settembre–3 ottobre 2026**:

- **221 schede progetto / 227 eventi**, non 221 opportunità commerciali attive;
- **12 collector**, smoke live e 30 giorni per ogni fonte;
- **208 test**, provenienza e replay idempotente superati;
- **0 errori fonte/giorno**, qualità **0 ERROR / 3 WARN / 110 INFO**;
- mancanti: nome 2, MW 58, provincia singola 8, expediente 41;
- tutti gli 8 casi senza provincia singola sono multi-provincia, senza forzatura geografica;
- REE: 931 nodi, snapshot 2026-10-01; MITECO: 71.727 impianti, acquisizione 2026-10-04, 8 match esatti conservativi.

`CURRENT_STATE.md` riporta limiti, run, metriche e prossimi passi. La copertura nazionale delle fonti non è ancora completa. Artifact integrato `backfill-30d-output`: **11310701073**; report originale `reports/validation_metrics.json`.

## Fonti operative

Bollettini: **BOE, BOCYL, BOA, BOJA, DOCM, DOE, BORM, BOCM, DOG**: BOE nazionale e 8 delle 17 comunità autonome.

Altri collector: **MITECO_SABIA, AND_PUBLIC, GVA_PUBLIC**. SABIA copre milestone ENTRY/CONSULT datati, non tutte le variazioni amministrative. GVA è già integrato: il precedente ZIP `spain_radar_gva_preview_55ecc9d.zip` è superato e non va applicato a `main`.

Enrichment: **INE comuni**, **REE capacità/accesso**, **MITECO RAIPEE**. Dati di rete aggregati non confermano l'accesso di un singolo progetto; matching del registro conservativo.

Le altre fonti nel registry `config/sources.json` restano `implemented=false` fino a probe, collector reale, test, smoke live, backfill e assenza di errori strutturali. GVA non equivale a un collector DOGV. Mancano nove bollettini autonomici, oltre alle ulteriori famiglie di fonti indicate nella roadmap.

## Galicia: DOG datato e inventario storico distinti

Il collector **DOG è attivo nel comando ordinario**. Usa il calendario ufficiale, le sezioni delle edizioni datate e gli HTML originali; separa i progetti compresi nello stesso atto. La validazione dedicata **37220564261** e quella integrata **37220893072** sono SUCCESS.

Nel backfill: **21 edizioni, 817 voci degli indici, 2 pubblicazioni pertinenti e 3 progetti**. Porto Barroso: FV 0,99 MW, autorizzazione di ampliamento; la potenza è quella finale, non l'incremento. Monte Arca Norte e Sur: eolico 20 MW ciascuno, informazioni pubbliche sulle richieste, non autorizzazioni concesse. La durata dichiarata di 12 mesi è conservata senza inventare date di cantiere.

`app.galicia_archive` acquisisce separatamente gli archivi ufficiali regionali: **487 record**, non progetti unici. Il primo inventario crea una BASELINE, **non nuove opportunità**. La rimozione da un elenco non implica ritiro del progetto. Le date degli atti, i periodi di consultazione e le date nei link DOG restano separati dalle date web ignote. Gli allegati sono indicizzati, non acquisiti.

Il confronto DOG–inventario usa solo documento ufficiale o riferimento amministrativo esatto, senza modificare le date dell'archivio. Nel backfill corrente: confronto eseguito, **0 match esatti**. L'inventario non incrementa il conteggio dei dodici collector.

## Catalunya: fonti in verifica, non ancora attive

Acquisiti e riconciliati i dataset ufficiali completi FV/eolico: **358 e 137 righe**, rispettivamente. Le righe per comune, le potenze zero secondarie e gli impianti in servizio richiedono una rappresentazione distinta dal feed dei nuovi progetti. Le date di aggiornamento del dataset e delle riunioni ambientali non sono date di pubblicazione dei singoli permessi. Nessuna scheda catalana è stata aggiunta al radar con date inventate.

Checkpoint: `docs/sources/catalunya.md`. DOGC è alla verifica della navigazione e dei servizi pubblici: `docs/sources/dogc.md`. Nessun collector Catalunya/DOGC viene dichiarato implementato in questa fase.

## Lifecycle, scoring ed EPC/BoP

Eventi: PUBLIC_INFO, DIA, PRIOR_AUTH, CONSTRUCTION_AUTH, PUBLIC_UTILITY, EXPROPRIATION, MODIFICATION, WITHDRAWN, DENIED, PROCEDURE_ENDED; SABIA conserva il proprio perimetro di milestone documentati.

Stati derivati: EARLY, PERMITTING, AUTHORIZED, PRECONSTRUCTION, BLOCKED. Una richiesta di autorizzazione non equivale a una concessione.

Score e priorità commerciali sono separati dal dato amministrativo. EPC/BoP usa evidenze esplicite in una tabella separata e gli stati EPC_CONFIRMED, EPC_CANDIDATE, EPC_UNKNOWN. Promotore non significa EPC. La ricerca esterna dei contractor resta successiva all'ampliamento delle fonti pubbliche di discovery.

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

Inventario Galicia separato:

```bat
.\.venv\Scripts\python.exe -m app.galicia_archive
```

## Output

- Database: `data/spain_renewables.sqlite`.
- Variazioni: `reports/change_reports/changes_latest.html`.
- Copertura e qualità: `reports/coverage_latest.html`, `reports/quality_issues_latest.html`.
- EPC/BoP: `reports/epc_bop_evidence_latest.html` e CSV.
- Vista provinciale: `reports/province_view_latest.html` e CSV.
- REE/MITECO: `reports/ree_capacity_latest.csv`, `reports/miteco_registry_latest.csv`, `reports/miteco_exact_matches_latest.csv`.
- Lacune e contrasti della fonte: `reports/andalucia_public/source_gaps.html`, `reports/gva_public/source_flags.html`.
- DOG: `reports/dog/coverage.json`, `raw/`, `galicia_links.json`; evidenze dei campi nella tabella separata `regional_public_metadata`.
- Inventario Galicia: `reports/galicia_archive/index.html`, `inventory.json`, `inventory.csv`, `changes.json`, `window_audit.json`; baseline locale persistente `data/galicia_archive_baseline.json`.
- Dashboard: `docs/index.html`.

La vista provinciale distingue MW identificati, MW sconosciuti, progetti multi-provincia e potenze di gruppo non allocate; non duplica potenze nelle province.

## Regole

URL, external_id, date e testi originali sempre preservati. Meglio campo vuoto che dato inventato. Conflitti segnalati, non risolti arbitrariamente. Nomi mancanti non ricavati dal promotore. La qualità strutturale non garantisce che ogni campo sia già completo o semanticamente perfetto.
