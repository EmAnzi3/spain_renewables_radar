# Spain Renewables Radar

Radar per progetti **fotovoltaici, eolici, BESS e ibridi** spagnoli, da fonti **ufficiali e gratuite**. Nessun aggregatore commerciale.

**Fonti → eventi amministrativi → progetto unico → lifecycle → enrichment → scoring separato → quality gate → report/dashboard.** Gli inventari senza date verificabili non diventano nuovi eventi.

## Stato — 6 ottobre 2026

**La PR #2 è integrata su main. Classificazione BOPV completata sul perimetro verificato; disponibilità live GVA ancora bloccata.** I test del codice sono verdi, ma non certificano una fonte che non risponde.

Il codice contiene **13 collector**. GVA usa connessioni anonime riutilizzate, richieste distanziate, retry limitati e catalogo completo riutilizzabile soltanto nello stesso run/attempt dopo verifica di tutti gli originali e nuovi controlli live alle estremità. Gli orari dei singoli file sono controllati e non modificati. I job dedicato/integrato sono serializzati; il preflight GVA ferma il backfill prima di acquisire inutilmente le altre dodici fonti quando il portale è irraggiungibile.

**Il run integrato 37430217829 fallisce nel preflight GVA**, prima di ricevere dati HTTP. Lo stesso endpoint fallisce anche nel confronto ARM64 37430471860. I due accessi ufficiali cindi/mediambient risolvono lo stesso indirizzo e sono andati in timeout; non è accertata la causa interna del disservizio. Nessuna fonte è stata esclusa o sostituita con dati vecchi. Il workflow ordinario non è stato spostato su ARM64.

**BOPV:** indice verificato da 306 disposizioni; cinque atti classificati in **sei impianti energetici e un lead industriale per autoconsumo**, con evidenza del paragrafo. Run **37428902802 — SUCCESS**, ripetuto su main nel run **37430217754 — SUCCESS**. **BOPV resta disabilitato nel radar:** classificatore completato non significa collector live abilitato. Restano persistenza, smoke e backfill del nuovo collector.

Suite locale completa: **586 test superati**, inclusi 34 nuovi casi BOPV; controlli unitari su main verdi. Stato, artifact verificati, limiti e storico: **CURRENT_STATE.md**, **docs/validation/2026-10-06-gva-bopv-completion.json**.

La correzione **BESS Almagro I 7,2 MW, Ciudad Real, PUBLIC_INFO/EARLY** resta validata dalla prova DOCM dedicata 37420987930. Migrazione hash-locked con backup e transazione, senza alterazione degli originali.

L'ultimo backfill completo riuscito rimane **37406054339**, finestra **6 settembre–5 ottobre 2026**, **256 schede / 262 eventi**, qualità **0 ERROR / 9 WARN / 184 INFO**. **Il suo artifact contiene il vecchio Almagro errato:** non attribuirgli retroattivamente la correzione attuale né sommare i sei impianti BOPV ai suoi conteggi.

## Fonti e significato dei dati

Bollettini: **BOE, BOCYL, BOA, BOJA, DOCM, DOE, BORM, BOCM, DOG, DOGC**. Portali: **AND_PUBLIC, GVA_PUBLIC, MITECO_SABIA**. Bollettini CCAA **9/17**. Non operativi: **DOGV, BON, BOPV, BOPA, BOCANT, BOC-CAN, BOIB, BOR**. GVA_PUBLIC non equivale a DOGV.

SABIA conserva milestone ENTRY/CONSULT, non autorizzazioni dedotte dallo stato corrente. INE, REE e RAIPEE sono enrichment. Matching conservativo; i dati aggregati di rete non provano l'accesso di un progetto.

Un progetto accumula gli eventi senza essere ricreato a ogni pubblicazione. MW/MWh/kVA/MVA, potenze esistenti e ampliamenti sono separati. Una richiesta non è un'autorizzazione; una DIA non prova il cantiere. Stati EARLY, PERMITTING, AUTHORIZED, PRECONSTRUCTION, BLOCKED; score commerciale separato. Promotore non significa EPC.

Inventari Catalunya/Galicia separati: BASELINE non significa nuove opportunità, NOT_SEEN non significa ritiro. I lead municipali DOGC e l'autoconsumo industriale BOPV non vengono trasformati in permessi energetici falsi. Documentazione nelle rispettive schede in `docs/sources/`.

## Avvio Windows

```bat
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
aggiorna_radar_spagna.bat
```

Launcher ordinario: **ultimi sette giorni**, invariato. Aggiornare prima la copia locale da main. Non applicare il vecchio `spain_radar_gva_preview_55ecc9d.zip`.

Backfill con verifica della copertura:

```bat
.\.venv\Scripts\python.exe -m app.run_pipeline --days 30 --strict-coverage
```

Verifica GVA autonoma, senza eventi o database:

```bat
.\.venv\Scripts\python.exe -m app.gva_preflight
```

È utile per confrontare la raggiungibilità da una connessione diversa dai runner. Il suo successo verifica il catalogo, non tutta la semantica o il backfill a tredici fonti. In caso di errore lascia `reports/gva_public/preflight.json` con causa e tempi, senza recuperare vecchi dati come nuovi.

Inventari separati:

```bat
aggiorna_inventario_catalogna.bat
.\.venv\Scripts\python.exe -m app.galicia_archive
```

Non eliminare le baseline per aggiornamenti ordinari. Un report precedente non è una nuova acquisizione riuscita; per Catalunya controllare `reports/catalunya_inventory/run_status.json`.

## Output

Database `data/spain_renewables.sqlite`; variazioni `reports/change_reports/changes_latest.html`; copertura `reports/coverage_latest.html`; qualità `reports/quality_issues_latest.html`; dashboard generata `docs/index.html`.

Vista provinciale e CSV: `reports/province_view_latest.html`; EPC/BoP: `reports/epc_bop_evidence_latest.html`; REE/RAIPEE e originali regionali in `reports/`. Evidenza GVA: `reports/gva_public/preflight.json`, `coverage.json`, `transport_attempts.json` e originali. Correzioni Almagro: `reports/docm_storage/`.

Classificazione BOPV, artifact **bopv-classification-output**: `index.html`, `assets.csv`, `classified_documents.json`, `originals/`, `validation_metrics.json`. Non è un pacchetto di codice da applicare e non aggiunge record al database ordinario. Tabelle presenti soltanto nei PDF sono segnalate, non inventate.

Un commit non aggiorna il database sul PC e non pubblica automaticamente un sito. Test verdi, classificazione su originali e acquisizione live sono prove diverse: consultare il checkpoint prima di dichiarare una nuova certificazione completa.
