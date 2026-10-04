# Spain Renewables Radar

Radar per progetti **fotovoltaici, eolici, BESS e ibridi** in Spagna, da fonti **ufficiali e gratuite**. Nessun aggregatore commerciale.

## Architettura

Fonti ufficiali → eventi amministrativi → progetto unico → lifecycle → enrichment INE/REE/MITECO → scoring separato → quality gate → report/dashboard.

Gli inventari senza date di pubblicazione verificabili sono moduli separati: non vengono trasformati in nuovi eventi del radar.

## Stato certificato della pipeline ordinaria

**[Run 37220893072 — SUCCESS](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37220893072)**, codice `f4a88a6fe7a8706b5e30a52d168b93e060beaaeb`, finestra **4 settembre–3 ottobre 2026**:

- **221 schede progetto / 227 eventi**, non 221 opportunità commerciali attive;
- **12 collector**, smoke live e 30 giorni per ogni fonte;
- **208 test nel run certificato**, provenienza e replay idempotente superati;
- **0 errori fonte/giorno**, qualità **0 ERROR / 3 WARN / 110 INFO**;
- mancanti: nome 2, MW 58, provincia singola 8, expediente 41;
- tutti gli 8 casi senza provincia singola sono multi-provincia, senza forzatura geografica;
- REE: 931 nodi, snapshot 2026-10-01; MITECO: 71.727 impianti, acquisizione 2026-10-04, 8 match esatti conservativi.

`CURRENT_STATE.md` riporta limiti, run, metriche e prossimi passi. La copertura nazionale delle fonti non è ancora completa. Le successive verifiche del codice hanno raggiunto **268 test superati**, ma non costituiscono una nuova certificazione live integrata. L'inventario Catalunya è stato validato separatamente; DOGC non è ancora operativo.

## Fonti operative

Bollettini: **BOE, BOCYL, BOA, BOJA, DOCM, DOE, BORM, BOCM, DOG**.

Altri collector: **MITECO_SABIA, AND_PUBLIC, GVA_PUBLIC**. SABIA copre milestone ENTRY/CONSULT datati, non tutte le variazioni amministrative. GVA è già integrato: il precedente ZIP `spain_radar_gva_preview_55ecc9d.zip` è superato e non va applicato a `main`.

Enrichment: **INE comuni**, **REE capacità/accesso**, **MITECO RAIPEE**. Dati di rete aggregati non confermano l'accesso di un singolo progetto; matching del registro conservativo.

Le altre fonti nel registry `config/sources.json` restano `implemented=false` fino a probe, collector reale, test, smoke live, backfill e assenza di errori strutturali. GVA non equivale a un collector DOGV. L'inventario Catalunya non equivale a un collector DOGC. Copertura dei bollettini CCAA: **8/17**.

## Galicia: pubblicazioni datate e inventario storico distinti

**DOG** è operativo nella pipeline: calendario ufficiale, edizioni e sezioni datate, avvisi HTML originali. La validazione dedicata `37220564261` e quella integrata `37220893072` hanno verificato 30 giorni, 21 edizioni, 817 voci degli indici, 2 pubblicazioni pertinenti e 3 progetti. Le due sezioni Monte Arca sono conservate come due impianti; le durate dei lavori non diventano date di avvio/fine. Per Porto Barroso la potenza finale dell'ampliamento è distinta dalla nuova potenza aggiuntiva.

`app.galicia_archive` acquisisce e riconcilia gli archivi ufficiali regionali e le schede HTML, con originali e confronto tra snapshot. Il primo inventario crea una BASELINE, **non nuove opportunità**. La rimozione da un elenco non implica ritiro del progetto.

Le date degli atti, i periodi di consultazione e le date nei link DOG restano separati dalle date web ignote. I documenti allegati sono indicizzati, non acquisiti. L'inventario non crea eventi nel database. Il collegamento al DOG usa soltanto documenti o riferimenti amministrativi esatti: nella finestra certificata il confronto ha prodotto zero collegamenti, senza associazioni inventate.

## Catalunya: inventario operativo, DOGC ancora in verifica

**[Validazione inventario 37241609997 — SUCCESS](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37241609997)**, codice `b9e0cb7076c84743ace93c658979f20af60c07dc`: **242 test**, due acquisizioni live indipendenti con paginazione, conteggi/versioni riconciliati, originali verificati e baseline persistente. Seconda acquisizione senza variazioni; replay idempotente.

I dataset ufficiali contengono **137 righe eoliche e 358 fotovoltaiche**. Sono righe comunali, non conteggi di impianti. I **434 gruppi diagnostici** includono **82 righe senza riferimento mantenute separate**: non sono un censimento certificato di progetti unici. Potenze e superfici totali ripetute tra comuni non vengono sommate; zeri e conflitti della fonte restano visibili. Nessuna data di pubblicazione, autorizzazione o lavori viene dedotta dalla data di aggiornamento del dataset o della riunione ambientale.

Modulo `app.catalunya_inventory`, launcher `aggiorna_inventario_catalogna.bat`, report HTML/CSV/JSON e variazioni. **Nessun evento datato creato, nessuna modifica ai dodici collector ordinari.** Dettagli: `docs/sources/catalunya.md` e `docs/validation/2026-10-05-catalunya-inventory.json`.

**DOGC non è ancora un collector abilitato.** Calendario, sommari e servizio di ricerca sono raggiungibili con verifica TLS attiva. Nell'audit 5 settembre–4 ottobre 2026 sono stati acquisiti i sommari di 20 edizioni principali e tre allegati; la riconciliazione indipendente si è fermata perché la ricerca paginata ripete sette avvisi. L'esportazione CSV alternativa è andata in timeout. I testi integrali non sono stati acquisiti e l'indice non è certificato. Stato e ripartenza: `docs/sources/dogc.md`, `docs/validation/2026-10-05-dogc-checkpoint.json`.

## Lifecycle, scoring ed EPC/BoP

Eventi: PUBLIC_INFO, DIA, PRIOR_AUTH, CONSTRUCTION_AUTH, PUBLIC_UTILITY, EXPROPRIATION, MODIFICATION, WITHDRAWN, DENIED, PROCEDURE_ENDED; SABIA conserva il proprio perimetro di milestone documentati.

Stati derivati: EARLY, PERMITTING, AUTHORIZED, PRECONSTRUCTION, BLOCKED. Una richiesta di autorizzazione non equivale a una concessione.

Score e priorità commerciali sono separati dal dato amministrativo. EPC/BoP usa evidenze esplicite in una tabella separata e gli stati EPC_CONFIRMED, EPC_CANDIDATE, EPC_UNKNOWN. Promotore non significa EPC. La ricerca esterna dei contractor resta successiva all'ampliamento delle fonti pubbliche di discovery.

## Avvio Windows

Configurazione iniziale e radar ordinario:

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

Inventario Catalunya separato, con lo stesso ambiente Python già configurato:

```bat
aggiorna_inventario_catalogna.bat
```

Equivalente da terminale:

```bat
.\.venv\Scripts\python.exe -m app.catalunya_inventory
```

Il launcher apre il report dopo un'acquisizione riuscita. In caso di errore consultare `reports/catalunya_inventory/run_status.json`: il precedente inventario valido non deve essere interpretato come un nuovo aggiornamento riuscito. Non eliminare la baseline locale per un aggiornamento ordinario: perderesti il riferimento necessario al confronto delle variazioni. Non è stato aggiunto un aggiornamento pianificato automatico.

## Output

- Database: `data/spain_renewables.sqlite`.
- Variazioni: `reports/change_reports/changes_latest.html`.
- Copertura e qualità: `reports/coverage_latest.html`, `reports/quality_issues_latest.html`.
- EPC/BoP: `reports/epc_bop_evidence_latest.html` e CSV.
- Vista provinciale: `reports/province_view_latest.html` e CSV.
- REE/MITECO: `reports/ree_capacity_latest.csv`, `reports/miteco_registry_latest.csv`, `reports/miteco_exact_matches_latest.csv`.
- Lacune e contrasti della fonte: `reports/andalucia_public/source_gaps.html`, `reports/gva_public/source_flags.html`.
- DOG: `reports/dog/coverage.json`, `reports/dog/raw/`, `reports/dog/galicia_links.json`.
- Galicia: `reports/galicia_archive/index.html`, `inventory.json`, `inventory.csv`, `changes.json`, `window_audit.json`; baseline locale persistente `data/galicia_archive_baseline.json`.
- Catalunya: `reports/catalunya_inventory/index.html`, `run_status.json`, `latest.json`; ogni cartella `snapshots/` conserva report, inventario JSON/CSV, variazioni, metriche e originali. Baseline persistente `data/catalunya_inventory_baseline.json`.
- Dashboard ordinaria: `docs/index.html`. Gli inventari separati non vengono automaticamente pubblicati nella dashboard.

La vista provinciale distingue MW identificati, MW sconosciuti, progetti multi-provincia e potenze di gruppo non allocate; non duplica potenze nelle province.

## Regole

URL, external_id, date e testi originali sempre preservati. Meglio campo vuoto che dato inventato. Conflitti segnalati, non risolti arbitrariamente. Nomi mancanti non ricavati dal promotore. La qualità strutturale non garantisce che ogni campo sia già completo o semanticamente perfetto. Una prova fallita o un risultato incompleto non viene presentato come fonte certificata.
