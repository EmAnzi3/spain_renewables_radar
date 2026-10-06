# CURRENT STATE — Spain Renewables Radar

Checkpoint: **6 ottobre 2026, Europe/Rome**. Lavoro su `main`; **13 collector operativi**, BOPV ancora disabilitato. La PR #1 è già integrata: non occorre ripetere il merge. Distinguere codice pubblicato, prova dedicata e backfill integrato.

## Esiti attuali

| Blocco | Stato verificato |
|---|---|
| Correzione DOCM Almagro | Pubblicata in `61f98ce053d8dc3527d6f03d7e6f9446747595e4` |
| DOCM dedicato, 30 giorni | **37420987930 — SUCCESS** |
| BOPV indice, ricerca, sommari e date | **37420987792 — SUCCESS**, non un collector abilitato |
| Codice delle due prove dedicate | `b9752fcc8b5f492bc97f03ccdf83b1857de1b039` |
| Suite ordinaria | **530 test**; run `37420987798 — SUCCESS` |
| Contratti BOPV | **26 test**, eseguiti separatamente nel workflow dedicato |
| Politica recupero runner | Run `37420987829`: test SUCCESS, recupero SKIPPED correttamente |
| Backfill integrato dopo la correzione | **37418379045, tentativi 1 e 2 — FAILURE**, bloccati durante lo smoke dalla fonte GVA |
| Ultimo backfill integrato completato | **37406054339 — SUCCESS**, precedente alla correzione Almagro |

Checkpoint dettagliato, digest degli artifact e limiti: `docs/validation/2026-10-06-almagro-bopv.json`. La presente revisione è soltanto documentale rispetto al codice delle prove dedicate.

## Almagro I: correzione chiusa nella validazione dedicata

La pubblicazione **DOCM-2026-7037**, del **5 ottobre 2026**, riguarda una richiesta autorizzativa per un accumulo abbinato al FV esistente. Il parser precedente assegnava alla batteria i **7,4 MW del fotovoltaico**.

Risultato ora verificato: **BESS Almagro I**, **BESS 7,2 MW**, comune **Almagro**, provincia **Ciudad Real**, **Castilla-La Mancha**, expediente **13270209226**, project_key **822a676aca030c14a431**, evento **PUBLIC_INFO / EARLY**. Il contesto di ibridazione resta conservato. Non è un'autorizzazione concessa.

Restano separate le quantità originali: **7,4 MW** FV preesistente, **5,016 MWh per contenitore**, **3.600 kVA**, **7,2 MW BESS**, **8 MVA**, **14,6 MW** dopo ibridazione e **6.690.000 W** di accesso. Nessuna somma impropria o conversione fra potenza attiva, apparente ed energia. Nessuna data lavori o EPC inventati.

`app.docm_storage` usa la formulazione esplicita del documento, non un elenco di ID. Evidenze mancanti o contrastanti lasciano campi vuoti e producono flag. Sono conservati raw_text, hash e intervalli del testo. Il riconoscimento INE accetta anche **término municipal** al singolare, senza usare il domicilio del promotore.

### Riparazione dei database esistenti

La riparazione del vecchio Almagro è separata dal quality gate: richiede hash originale esatto, vecchi valori attesi e un solo evento nel progetto. Crea un backup SQLite, usa una transazione e registra la modifica. Casi diversi, condivisi o con sorgente cambiata si fermano per revisione.

Su una copia del database integrato precedente sono cambiati **solo nome, tecnologia, MW e provincia del progetto Almagro**. La provincia dell'evento originale non viene riscritta dall'enrichment. Chiave, external_id, testo, URL, date e lifecycle restano invariati. La seconda esecuzione produce zero correzioni. È una prova di migrazione su una copia, non un nuovo download live di tutte le fonti.

### Prova live dedicata

**Run 37420987930 — SUCCESS**, periodo **6 settembre–5 ottobre 2026**: **30 giorni DOCM, 18 eventi / 18 progetti, zero errori fonte/giorno e zero errori strutturali**. Verificati Almagro nel database dell'artifact, provenienza, geografia INE e idempotenza. Artifact **11392454466**, **78.157 byte**, SHA256 **ecd62b74531b5a322e8ee4ba1e3c594b9b96c94bda8681f0f47ba986a52fea6e**, scaricato e verificato. Metodo: `docs/sources/docm-storage.md`.

**La prova DOCM non sostituisce il backfill delle 13 fonti.**

## GVA: nuovo backfill integrato ancora bloccato

Il run **37418379045**, codice funzionale Almagro `61f98ce`, è stato eseguito due volte senza escludere fonti. Nel primo tentativo: **HTTP 400** sulla pagina iniziale GVA. Nel secondo: le pagine iniziali rispondono, ma la **pagina 15** termina con ReadTimeout e due connessioni interrotte, esaurendo il budget limitato. Lo smoke fallisce; backfill di 30 giorni e gate integrato sono **SKIPPED**, non certificati.

Artifact del secondo tentativo **11392916871**, **19.231.756 byte**, SHA256 **6f65bcc3639dfdbb22948ff59915c183664e9e0e5dd25c41225a09edc4b4cc30**, scaricato e verificato. Le ricevute conservano la progressione fino alla pagina 14 e gli errori sulla 15. Nessuna pagina mancante è sostituita da dati fittizi o da cache dichiarate live. Le tre date GVA dello smoke sono ERROR.

Non è stato introdotto un ciclo di rilanci illimitato. Il recupero automatico riguarda soltanto runner non assegnati, non errori HTTP o dei dati. Il suo job è ora limitato ai propri test senza dipendenze: i test BOPV nella stessa directory avevano causato un errore di importazione nel job di policy, corretto senza modificare i criteri di rilancio.

## Ultimo dataset integrato riuscito — prima della correzione

**Run 37406054339 — SUCCESS**, codice **88201b5a2e2f5b35c39ac028d44c4d3e155a3391**, periodo **6 settembre–5 ottobre 2026**:

- **256 schede progetto / 262 eventi**, 13 fonti per 30 giorni;
- **0 errori fonte/giorno**, qualità **0 ERROR / 9 WARN / 184 INFO**;
- mancanti: nome **2**, MW **69**, provincia singola **10**, expediente **39**;
- geografia: **9 multi-provincia e 1 irrisolto**, che era Almagro;
- **648,16 MW multi-provincia** separati; **30 MW del gruppo SABIA 20260224** non allocati;
- Begues I–VII sono distinti: ciascuno **5,04 MW / 20,06 MWh**, PERMITTING; Gandia Hive è DENIED/BLOCKED.

**Questo artifact conserva il vecchio valore errato di Almagro.** Non attribuire retroattivamente al vecchio dataset la correzione del codice attuale. Artifact **11388095924**, **91.685.094 byte**, SHA256 **fae2b7a9b3a15d502bc04ab1b81110b74d6fafceac70c4de5802e61e632f08d6**, verificato.

Eventi per fonte: AND_PUBLIC 8; BOA 22; BOCM 4; BOCYL 32; BOE 38; BOJA 7; BORM 12; DOCM 18; DOE 8; DOG 3; DOGC 40; GVA_PUBLIC 16; MITECO_SABIA 54. I checkpoint a 240/246 e 221/227 sono relativi a versioni o finestre diverse: sottrarre i totali non misura il contributo di una fonte.

## BOPV — indice riconciliato, collector da completare

**Run 37420987792 — SUCCESS**, codice `b9752fcc8b5f492bc97f03ccdf83b1857de1b039`, periodo **6 settembre–5 ottobre 2026**:

- **306 disposizioni univoche**, ricerca completa su **31 pagine**;
- confronto con tutti i sommari delle **21 edizioni** dei calendari ufficiali;
- **30 giorni rendicontati**, inclusi **9 senza edizione dichiarata dalla fonte**;
- **zero omissioni e zero conflitti nei titoli**;
- **5 avvisi candidati**, con HTML, identità, titolo, data di pubblicazione ed edizione verificati;
- originali conservati; ricostruzione locale dei sommari e verifica di **62 ricevute/file originali**.

Artifact **11393276447**, **753.694 byte**, SHA256 **35f211924f8309c2b14a8e7d6990cbd70ee86e77d076db97671ffb7d9bd8a885**, scaricato e verificato. Testate del menu, parametri di visualizzazione e apici HTML sono gestiti sulla base dei file originali, senza ignorare ID, date, numeri o differenze sostanziali.

**BOPV resta implemented=false e crea zero eventi.** Cinque avvisi non equivalgono a cinque impianti: alcuni contengono più progetti. Restano classificazione del dispositivo, estrazione per impianto/componente, collector, smoke, backfill e verifica integrata. Metodo e ripartenza: `docs/sources/bopv.md`.

## Perimetro e prossime attività

Collector: **BOE, BOCYL, BOA, BOJA, DOCM, DOE, BORM, BOCM, DOG, DOGC, AND_PUBLIC, GVA_PUBLIC, MITECO_SABIA**. Bollettini CCAA **9/17**. INE, REE e RAIPEE sono enrichment. Mancanti: **DOGV, BON, BOPV, BOPA, BOCANT, BOC-CAN, BOIB, BOR**.

Priorità: ottenere una nuova certificazione integrata quando GVA risponde completamente; completare il collector BOPV; proseguire con altre fonti regionali, quindi PLACSP, IDAE/BDNS, concorsi MITECO/ITJ e contesto CNMC. La ricerca esterna EPC/BoP resta successiva alla discovery.

Inventari Catalunya/Galicia separati dagli eventi datati: BASELINE non significa nuove opportunità e NOT_SEEN non significa ritiro. SABIA mantiene ENTRY/CONSULT; la rete REE non prova l'accesso del singolo impianto. Restano espliciti MW sconosciuti, potenze di gruppo, multi-provincia e difformità delle fonti.

## Uso e vincoli

BAT ordinario: `aggiorna_radar_spagna.bat`, ultimi 7 giorni. La riparazione del vecchio Almagro è nella pipeline anche per eventi già salvati, soltanto quando gli invarianti coincidono. Un aggiornamento remoto non modifica il database sul PC né pubblica automaticamente un sito.

Solo fonti ufficiali/gratuite; nessun aggregatore commerciale. Preservare external_id, URL, raw_text e date. Promotore distinto da EPC; richiesta distinta da concessione; scoring separato dal lifecycle. Meglio un campo vuoto che un dato inventato. Test verdi e prove dedicate non diventano certificazioni integrate complete.
