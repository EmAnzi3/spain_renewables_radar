# Spain Renewables Radar

Radar per progetti **fotovoltaici, eolici, BESS e ibridi** in Spagna, da fonti **ufficiali e gratuite**. Nessun aggregatore commerciale.

## Architettura

Fonti ufficiali → eventi amministrativi → progetto unico → lifecycle → enrichment INE/REE/MITECO → scoring separato → quality gate → report/dashboard.

Gli inventari senza date di pubblicazione verificabili sono moduli separati: non vengono trasformati in nuovi eventi del radar.

## Codice operativo e ultima certificazione integrata

Questa revisione include **13 collector**, compreso **DOGC** nel comando ordinario e nel registry. L'ultima prova integrata completata è il **[run 37350555017 — SUCCESS](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37350555017)**, codice `ca598cc0f1e685652c6af58c83c85f6186fafd9e`, finestra **5 settembre–4 ottobre 2026**:

- **240 schede progetto / 246 eventi**, non 240 cantieri o opportunità commerciali attive;
- **13 collector × 30 giorni**, stessa finestra contigua, smoke live e backfill integrato superati;
- **0 errori fonte/giorno**, qualità **0 ERROR / 9 WARN / 157 INFO**;
- mancanti: nome **2**, MW **62**, provincia singola **9**, expediente **41**;
- i nove casi senza provincia singola sono tutti multi-provincia: **zero province realmente irrisolte**;
- controlli di identità, provenienza e riesecuzione senza duplicazioni superati;
- REE: **931 nodi**; registro MITECO: **71.727 impianti**, **8 match esatti** conservativi.

La prova citata è stata eseguita sul branch della PR #1. Il suo esito non viene retroattivamente attribuito a un diverso commit o a un run post-merge. Lo stato effettivo dell'integrazione e dei workflow sul nuovo HEAD è nella [PR #1](https://github.com/EmAnzi3/spain_renewables_radar/pull/1). La chiusura documentale non modifica il codice funzionale validato.

L'artifact originale è stato verificato per dimensione e SHA256; il checkpoint persistente è `docs/validation/2026-10-05-thirteen-source.json`. `CURRENT_STATE.md` riporta limiti e prossimi passi. Il precedente risultato **221/227** appartiene alla diversa finestra **4 settembre–3 ottobre**: la differenza fra i totali non misura il contributo DOGC. La copertura nazionale delle fonti non è ancora completa.

## Fonti operative

Bollettini: **BOE, BOCYL, BOA, BOJA, DOCM, DOE, BORM, BOCM, DOG, DOGC**.

Altri collector: **MITECO_SABIA, AND_PUBLIC, GVA_PUBLIC**. SABIA copre milestone ENTRY/CONSULT datati, non tutte le variazioni amministrative. GVA_PUBLIC è distinto dal DOGV, che resta non implementato. Il precedente ZIP `spain_radar_gva_preview_55ecc9d.zip` è superato e non va applicato a `main`.

Enrichment: **INE comuni**, **REE capacità/accesso**, **MITECO RAIPEE**. Non sono ulteriori collector di discovery. Dati di rete aggregati non confermano l'accesso di un singolo progetto; il matching del registro è conservativo.

Copertura dei bollettini CCAA: **9/17**. Restano non operativi **DOGV, BON, BOPV, BOPA, BOCANT, BOC-CAN, BOIB, BOR**. Le fonti non implementate rimangono tali fino a probe, collector reale, test, smoke live, backfill e controlli strutturali. Non confondere il numero di fonti con la completezza di tutti i progetti spagnoli.

## Catalunya: DOGC datato e inventario separato

**DOGC è incluso nei 13 collector ordinari.** Nel backfill certificato: **1.525 disposizioni**, **48 PDF / 299 pagine**, **33 eventi energetici** su 33 chiavi di progetto. Gli altri candidati sono conservati separatamente: **11 lead municipali, una rettifica e tre atti fuori ambito**.

I 33 eventi sono **13 PUBLIC_INFO, 10 ENVIRONMENTAL_SCREENING, 1 DIA, 8 CONSTRUCTION_AUTH e 1 PUBLIC_UTILITY**. Stati derivati: **EARLY 13, PERMITTING 11, AUTHORIZED 9**. Una richiesta non è una concessione; uno screening ambientale non è un'autorizzazione alla costruzione; un'approvazione municipale non è un permesso energetico.

Per **11 eventi** non è pubblicata una potenza scalare: **6 conflitti**, **3 casi multicomponente**, **2 senza una potenza di progetto univoca**. Geografia integrata: **31 risolti e 2 multi-provincia**, senza duplicazione dei MW. Originali, pagine, quantità e riferimenti sono preservati e verificati dal replay. Metodo e storia delle verifiche: `docs/sources/dogc.md`.

L'inventario `app.catalunya_inventory` resta separato, validato dal run **37241609997**. Contiene **137 righe comunali eoliche e 358 fotovoltaiche**; **434 gruppi diagnostici**, inclusi **82 record senza riferimento tenuti separati**, non sono un censimento certificato di impianti unici. Potenze ripetute tra comuni non vengono sommate. La data del dataset non diventa la data di un progetto. Avvio: `aggiorna_inventario_catalogna.bat`; dettagli: `docs/sources/catalunya.md`.

## Galicia: pubblicazioni e inventario storico distinti

**DOG** è operativo: calendario ufficiale, edizioni/sezioni datate e HTML originali. Nella finestra integrata corrente: **20 edizioni, 786 voci degli indici, 2 pubblicazioni pertinenti e 3 progetti**. I due parchi Monte Arca rimangono distinti; una durata lavori non diventa una data di avvio/fine. Per Porto Barroso la potenza finale dell'ampliamento non è la sola potenza aggiuntiva.

`app.galicia_archive` è un inventario separato, con originali e confronto fra snapshot. La prima acquisizione crea una BASELINE, non nuove opportunità; una rimozione dall'elenco non prova il ritiro del progetto. Il collegamento al DOG richiede documenti o riferimenti amministrativi esatti: nel backfill corrente risultano **zero collegamenti esatti**, senza associazioni inventate.

## Andalucía: catalogo live completo

AND_PUBLIC acquisisce il catalogo pubblico live, non presume che un export offline abbia la stessa copertura. Nel run certificato: **13.636 record**, **200 record sovrapposti verificati** fra ricerche ordinate opposte, ricostruzione dagli originali superata. Restano **25 lacune originarie** nei metadati, esposte nel report. Retry e pagine alternative sono limitati; un errore persistente o una risposta incompleta non diventano un risultato valido.

## Lifecycle, scoring ed EPC/BoP

Eventi: PUBLIC_INFO, ENVIRONMENTAL_SCREENING, DIA, PRIOR_AUTH, CONSTRUCTION_AUTH, PUBLIC_UTILITY, EXPROPRIATION, MODIFICATION, WITHDRAWN, DENIED, PROCEDURE_ENDED; SABIA conserva il proprio perimetro di milestone documentati.

Stati derivati: EARLY, PERMITTING, AUTHORIZED, PRECONSTRUCTION, BLOCKED. Score e priorità commerciali sono separati dal dato amministrativo. EPC/BoP usa evidenze esplicite e gli stati EPC_CONFIRMED, EPC_CANDIDATE, EPC_UNKNOWN. Promotore non significa EPC. La ricerca esterna dei contractor resta successiva all'ampliamento delle fonti pubbliche di discovery.

## Avvio Windows

Configurazione iniziale e radar ordinario:

```bat
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
aggiorna_radar_spagna.bat
```

Il launcher ordinario usa già il collector DOGC: non occorre un secondo BAT per inserirlo nel radar. Aggiornare prima la propria copia della repository dal `main` integrato; il merge remoto non aggiorna automaticamente il database sul proprio PC.

Backfill manuale:

```bat
.\.venv\Scripts\python.exe -m app.run_pipeline --days 30
```

Inventari separati, usando lo stesso ambiente Python:

```bat
.\.venv\Scripts\python.exe -m app.galicia_archive
aggiorna_inventario_catalogna.bat
```

Per Catalunya, un errore non rimpiazza l'ultima baseline valida. Consultare `reports/catalunya_inventory/run_status.json`; non eliminare la baseline per un normale aggiornamento. Non è stato introdotto un nuovo scheduler.

## Output

- Database: `data/spain_renewables.sqlite`; dashboard generata: `docs/index.html`.
- Variazioni: `reports/change_reports/changes_latest.html`.
- Copertura e qualità: `reports/coverage_latest.html`, `reports/quality_issues_latest.html`.
- EPC/BoP e vista provinciale: `reports/epc_bop_evidence_latest.html`, `reports/province_view_latest.html`, con CSV.
- REE/MITECO: `reports/ree_capacity_latest.csv`, `reports/miteco_registry_latest.csv`, `reports/miteco_exact_matches_latest.csv`.
- Lacune regionali: `reports/andalucia_public/source_gaps.html`, `reports/gva_public/source_flags.html`.
- DOG: `reports/dog/coverage.json`, originali e collegamenti deterministici in `reports/dog/`.
- DOGC: `reports/dogc/index.html`, `coverage.json` e cartelle di acquisizione con PDF, pagine, eventi, metadati e categorie escluse. Solo gli eventi energetici entrano nel radar ordinario.
- Galicia: `reports/galicia_archive/index.html`; baseline locale `data/galicia_archive_baseline.json`.
- Catalunya inventario: `reports/catalunya_inventory/index.html`, `run_status.json`, snapshot e baseline locale `data/catalunya_inventory_baseline.json`.

La dashboard viene rigenerata dalla pipeline. Il workflow di validazione conserva database, report e dashboard nell'artifact; un merge del codice non è, da solo, una nuova acquisizione né una pubblicazione automatica su un sito. La vista provinciale separa MW identificati, sconosciuti, multi-provincia e potenze di gruppo non allocate, senza duplicarli.

## Regole

URL, external_id, date e testi originali sempre preservati. Meglio campo vuoto che dato inventato. Conflitti segnalati, non risolti arbitrariamente. Nomi mancanti non ricavati dal promotore. Il verde dei controlli non garantisce che ogni campo sia completo o semanticamente perfetto. Una prova fallita o incompleta non viene presentata come certificazione.
