# Spain Renewables Radar

Radar per progetti **fotovoltaici, eolici, BESS e ibridi** spagnoli, da fonti **ufficiali e gratuite**. Nessun aggregatore commerciale.

**Fonti → eventi amministrativi → progetto unico → lifecycle → enrichment → scoring separato → quality gate → report/dashboard.** Gli inventari senza date verificabili non vengono trasformati in nuovi eventi.

## Stato operativo — 6 ottobre 2026

Il codice su `main` include **13 collector**, con DOGC integrato e correzione **BESS Almagro I** pubblicata. La validazione dedicata DOCM di 30 giorni è **SUCCESS**, run **37420987930**: 18 eventi, zero errori, Almagro correttamente a **7,2 MW BESS, Ciudad Real**, PUBLIC_INFO/EARLY. La migrazione dei vecchi valori è controllata da hash dell'originale, backup, transazione e verifica degli invarianti; non altera l'identità o il testo della fonte.

**Il più recente backfill integrato dopo questa correzione non è verde:** run **37418379045**, due tentativi falliti durante lo smoke per errori di trasporto del portale GVA. Nessuna fonte è stata esclusa e nessun gate è stato abbassato per certificare dati parziali.

L'ultimo backfill completo riuscito rimane **37406054339**, codice `88201b5`, finestra **6 settembre–5 ottobre 2026**, con **256 schede / 262 eventi, 13 fonti, zero errori fonte/giorno**, qualità **0 ERROR / 9 WARN / 184 INFO**. Il suo artifact precede la correzione e contiene il vecchio valore Almagro: non confondere il codice attuale con i dati storici di quella prova.

**BOPV:** indice riconciliato nel run **37420987792 — SUCCESS**: 306 disposizioni, 21 edizioni, 30 giorni, cinque avvisi candidati verificati. **Non è ancora un collector operativo e non incrementa il conteggio delle fonti.**

Suite ordinaria: **530 test**; altri **26 test di contratto BOPV** nel workflow dedicato. Run delle prove dedicate sul codice `b9752fcc8b5f492bc97f03ccdf83b1857de1b039`. Stato, limiti e artifact verificati in **`CURRENT_STATE.md`** e **`docs/validation/2026-10-06-almagro-bopv.json`**.

## Fonti

Bollettini operativi: **BOE, BOCYL, BOA, BOJA, DOCM, DOE, BORM, BOCM, DOG, DOGC**. Portali: **AND_PUBLIC, GVA_PUBLIC, MITECO_SABIA**. Copertura dei bollettini CCAA: **9/17**.

Non operativi: **DOGV, BON, BOPV, BOPA, BOCANT, BOC-CAN, BOIB, BOR**. Un probe riuscito non equivale a un collector. GVA_PUBLIC non equivale a DOGV. SABIA conserva il perimetro di milestone **ENTRY/CONSULT**, non date web o autorizzazioni desunte dall'etichetta corrente.

Enrichment: **INE comuni**, **REE capacità/accesso**, **MITECO RAIPEE**. Non sono ulteriori fonti di discovery. Il matching del registro è conservativo; i valori di rete aggregati non provano l'accesso di un singolo progetto.

## Dati e decisioni

Un progetto accumula gli eventi successivi senza essere ricreato a ogni pubblicazione. Nomi, potenze, riferimenti, geografia e date mancanti restano vuoti. MW, MWh, MVA/kVA, potenza esistente e ampliamenti vengono mantenuti separati; i progetti multi-provincia non duplicano MW nei totali provinciali.

Stati derivati: **EARLY, PERMITTING, AUTHORIZED, PRECONSTRUCTION, BLOCKED**. Una richiesta non equivale a una concessione; screening ambientale e DIA non provano l'avvio dei lavori. Lo scoring commerciale non modifica il lifecycle. **Promotore non significa EPC**: EPC_CONFIRMED, EPC_CANDIDATE e EPC_UNKNOWN richiedono evidenze specifiche.

Il DOGC conserva separatamente lead municipali, rettifiche e avvisi non pertinenti. Il suo precedente fascicolo di 48 PDF/299 pagine non era un conteggio di 48 progetti. Gli atti successivi e i gruppi multi-impianto sono sottoposti agli stessi controlli; Begues I–VII rimangono sette impianti distinti, non una somma arbitraria.

Inventari **Catalunya** e **Galicia** separati: date di aggiornamento del dataset non diventano pubblicazioni dei progetti; BASELINE non significa nuove opportunità, NOT_SEEN non significa ritiro. Documentazione: `docs/sources/catalunya.md`, `docs/sources/dogc.md`, `docs/sources/bopv.md`, `docs/sources/docm-storage.md`.

## Avvio Windows

```bat
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
aggiorna_radar_spagna.bat
```

Il launcher ordinario usa gli **ultimi 7 giorni**. Aggiornare la copia locale da `main` prima di usarlo; non applicare il vecchio pacchetto `spain_radar_gva_preview_55ecc9d.zip`. Il codice remoto non aggiorna automaticamente il database sul PC.

Backfill di 30 giorni:

```bat
.\.venv\Scripts\python.exe -m app.run_pipeline --days 30 --strict-coverage
```

Inventari separati:

```bat
aggiorna_inventario_catalogna.bat
.\.venv\Scripts\python.exe -m app.galicia_archive
```

Non eliminare le baseline per aggiornamenti ordinari. Un errore di acquisizione non deve far apparire il vecchio report come una nuova acquisizione riuscita; per Catalunya controllare `reports/catalunya_inventory/run_status.json`.

## Output

Database: `data/spain_renewables.sqlite`. Variazioni: `reports/change_reports/changes_latest.html`. Copertura: `reports/coverage_latest.html`. Qualità: `reports/quality_issues_latest.html`. Dashboard generata: `docs/index.html`.

Vista provinciale: `reports/province_view_latest.html` e CSV, con MW sconosciuti e multi-provincia separati. EPC/BoP: `reports/epc_bop_evidence_latest.html`. REE/RAIPEE: esportazioni CSV in `reports/`.

Evidenze regionali: `reports/dog/`, `reports/dogc/`, `reports/gva_public/`, `reports/andalucia_public/`. Correzioni Almagro e backup: `reports/docm_storage/`. Inventari: `reports/catalunya_inventory/`, `reports/galicia_archive/`.

Il workflow di validazione conserva database, originali e report nell'artifact. **Un commit non pubblica automaticamente un sito e una validazione dedicata non certifica tutte le fonti.** Consultare il checkpoint per distinguere ultimo codice, ultima prova completa e problemi residui.
