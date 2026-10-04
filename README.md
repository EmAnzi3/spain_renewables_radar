# Spain Renewables Radar

Radar per progetti **fotovoltaici, eolici, BESS e ibridi** in Spagna, da fonti **ufficiali e gratuite**. Nessun aggregatore commerciale.

## Architettura

Fonti ufficiali → eventi amministrativi → progetto unico → lifecycle → enrichment INE/REE/MITECO → scoring separato → quality gate → report/dashboard.

## Stato certificato

**Run 37193300195 — SUCCESS**, codice `18518b1580380b0bb31c1e3cd9112da365682b0c`, finestra **4 settembre–3 ottobre 2026**:

- **218 schede progetto / 224 eventi**, non 218 opportunità commerciali attive;
- **11 collector**, smoke live e 30 giorni per ogni fonte;
- **157 test**, provenienza e replay idempotente superati;
- **0 errori fonte/giorno**, qualità **0 ERROR / 3 WARN / 109 INFO**;
- mancanti: nome 2, MW 58, provincia singola 8, expediente 41;
- tutti gli 8 casi senza provincia singola sono multi-provincia, senza forzatura geografica;
- REE: 931 nodi, snapshot 2026-10-01; MITECO: 71.727 impianti, acquisizione 2026-10-04, 8 match esatti conservativi.

`CURRENT_STATE.md` riporta limiti, run, metriche e prossimi passi. La copertura nazionale delle fonti non è ancora completa.

## Fonti operative

Bollettini: **BOE, BOCYL, BOA, BOJA, DOCM, DOE, BORM, BOCM**.

Altri collector: **MITECO_SABIA, AND_PUBLIC, GVA_PUBLIC**. SABIA copre milestone ENTRY/CONSULT datati, non tutte le variazioni amministrative. GVA è già integrato: il precedente ZIP `spain_radar_gva_preview_55ecc9d.zip` è superato e non va applicato a `main`.

Enrichment: **INE comuni**, **REE capacità/accesso**, **MITECO RAIPEE**. Dati di rete aggregati non confermano l'accesso di un singolo progetto; matching del registro conservativo.

Le altre fonti nel registry `config/sources.json` restano `implemented=false` fino a probe, collector reale, test, smoke live, backfill e assenza di errori strutturali. GVA non equivale a un collector DOGV.

## Galicia: inventario distinto dal radar datato

`app.galicia_archive` acquisisce e riconcilia gli archivi ufficiali regionali e le schede HTML, con originali e confronto tra snapshot. Il primo inventario crea una BASELINE, **non nuove opportunità**. La rimozione da un elenco non implica ritiro del progetto.

Le date degli atti, i periodi di consultazione e le date nei link DOG restano separati dalle date web ignote. I documenti allegati sono indicizzati, non acquisiti. Il modulo non crea eventi nel database progetti e non è incluso negli undici collector certificati. La validazione dell'inventario non certifica la completezza delle pubblicazioni storiche o correnti del DOG.

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
- Galicia: `reports/galicia_archive/index.html`, `inventory.json`, `inventory.csv`, `changes.json`, `window_audit.json`; baseline locale persistente `data/galicia_archive_baseline.json`.
- Dashboard: `docs/index.html`.

La vista provinciale distingue MW identificati, MW sconosciuti, progetti multi-provincia e potenze di gruppo non allocate; non duplica potenze nelle province.

## Regole

URL, external_id, date e testi originali sempre preservati. Meglio campo vuoto che dato inventato. Conflitti segnalati, non risolti arbitrariamente. Nomi mancanti non ricavati dal promotore. La qualità strutturale non garantisce che ogni campo sia già completo o semanticamente perfetto.
