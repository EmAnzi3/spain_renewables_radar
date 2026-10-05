# CURRENT STATE — Spain Renewables Radar

Checkpoint: **5 ottobre 2026, Europe/Rome**. Le date UTC originali delle acquisizioni restano conservate. Questa revisione contiene **13 collector ordinari, incluso DOGC**. La chiusura documentale aggiorna lo stato al backfill verificato senza modificare il codice funzionale.

## Certificazione integrata completata

- **[Run 37350555017 — SUCCESS](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37350555017)**, codice **`ca598cc0f1e685652c6af58c83c85f6186fafd9e`**.
- Branch della prova: **`fix/dogc-index-reconciliation`**, PR **#1**.
- Finestra **5 settembre–4 ottobre 2026**, completa e contigua per tutti i collector.
- **13 collector × 30 giorni = 390 righe fonte/giorno**, smoke live e backfill integrato superati.
- **240 schede progetto / 246 eventi**. Non sono 240 cantieri o opportunità commerciali attive.
- **0 errori fonte/giorno**, nessun giorno mancante; qualità **0 ERROR / 9 WARN / 157 INFO**.
- Mancanti: nome **2**, MW **62**, provincia singola **9**, expediente **41**.
- Tutti i nove casi senza provincia singola sono multi-provincia: **zero province irrisolte**.
- **648,16 MW multi-provincia** separati; i **30 MW di gruppo SABIA 20260224** non sono ripartiti né duplicati arbitrariamente.
- Controlli di identità, provenienza e replay idempotente superati; default del comando ordinario e registry coerenti.
- REE: **931 nodi**; registro MITECO: **71.727 impianti**, **8 match esatti** conservativi.
- **[Artifact 11363027158 — backfill-30d-output](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37350555017/artifacts/11363027158)**: **85.228.446 byte**, SHA256 **`433b176408cd12c657139cbe06f3578f1377f4744c40124195b72132728eb7b2`**, verificati contro i metadati GitHub e i byte scaricati.

Metriche originali: `reports/validation_metrics.json` nell'artifact. Checkpoint persistente verificato: `docs/validation/2026-10-05-thirteen-source.json`. Gli artifact contengono anche codice, test, originali, database e dashboard generata.

### Integrazione su main e controlli post-merge

La certificazione sopra è una prova reale sul codice indicato, non un risultato attribuibile automaticamente al nuovo commit di merge. **[PR #1](https://github.com/EmAnzi3/spain_renewables_radar/pull/1)** conserva lo stato effettivo del merge, il nuovo SHA e i run successivi. Prima di dichiarare una nuova certificazione di `main`, verificare conclusione, HEAD e artifact del relativo backfill; un workflow avviato o verde nei soli test non equivale al backfill completato.

L'aggiornamento finale del checkpoint è solo documentale. `app/`, `tests/`, `scripts/`, `config/`, dipendenze e workflow restano quelli del codice certificato. Il merge non aggiorna il database sul PC né pubblica automaticamente la dashboard su un sito. Il BAT ordinario rigenera dati e report nella copia locale aggiornata.

### Confronto con i checkpoint precedenti

Il run **37220893072**, codice **f4a88a6fe7a8706b5e30a52d168b93e060beaaeb**, certificava **12 fonti, 221 schede / 227 eventi** nella finestra **4 settembre–3 ottobre 2026**. Non confrontare i due totali come se la finestra fosse identica e non attribuire la differenza al solo DOGC. Il checkpoint storico è `docs/validation/2026-10-04-twelve-source.json`.

I run falliti, cancellati o incompleti restano evidenze storiche, non certificazioni. Il pacchetto `spain_radar_gva_preview_55ecc9d.zip` è superato: **non applicarlo su main**. Il precedente riepilogo esteso rimane consultabile nella [revisione precedente di CURRENT_STATE.md](https://github.com/EmAnzi3/spain_renewables_radar/blob/ca598cc0f1e685652c6af58c83c85f6186fafd9e/CURRENT_STATE.md); le sue indicazioni DOGC disabilitato/classificazione da completare sono superate da questo checkpoint.

### Eventi per fonte nel run corrente

| Fonte | Eventi |
|---|---:|
| AND_PUBLIC | 8 |
| BOA | 21 |
| BOCM | 4 |
| BOCYL | 32 |
| BOE | 40 |
| BOJA | 7 |
| BORM | 11 |
| DOCM | 17 |
| DOE | 8 |
| DOG | 3 |
| DOGC | 33 |
| GVA_PUBLIC | 14 |
| MITECO_SABIA | 48 |
| **Totale** | **246** |

## DOGC — collector classificato, integrato e validato

DOGC è il **tredicesimo collector ordinario**, con originale, data, pagine e decisione verificati. Nel run integrato: **1.525 disposizioni, 48 PDF / 299 pagine**, classificati in **33 eventi energetici, 11 lead municipali separati, una rettifica e tre atti fuori ambito**. Nessun candidato rimane fuori dal rendiconto.

Eventi: **13 PUBLIC_INFO, 10 ENVIRONMENTAL_SCREENING, 1 DIA, 8 CONSTRUCTION_AUTH, 1 PUBLIC_UTILITY**. Stati: **EARLY 13, PERMITTING 11, AUTHORIZED 9**. Sono **33 chiavi di progetto nel contributo DOGC**, non necessariamente 33 nuovi progetti rispetto a qualsiasi altra acquisizione o inventario.

Potenza scalare assente per **11 eventi**: **6 conflitti espliciti, 3 casi multicomponente, 2 senza potenza di progetto univoca**. I riferimenti e le quantità originali restano disponibili; MW, MWp/MWn, MWh e capacità di accesso non vengono sommati o scambiati arbitrariamente. Geografia integrata: **31 RESOLVED, 2 MULTI_PROVINCE**, senza MW duplicati nella vista provinciale. Questo risultato supera quello geografico della precedente validazione DOGC isolata, senza riscrivere l'evidenza storica.

Il gate ricostruisce esattamente PDF, semantica e campi proiettati; verifica originali, identità, date, geografia e replay senza duplicati. La revisione semantica congelata comprende **48 casi documento, 12 casi quantità e 4 casi riferimenti**. Le sei identità con conflitto di potenza restano **1053901, 1054244, 1054255, 1054269, 1054291, 1054428**.

Una richiesta non è una concessione. Screening ambientale non significa DIA né permesso di costruzione; un'approvazione locale non è un'autorizzazione energetica. Rettifiche e lead municipali non creano eventi energetici falsi. Nessuna data lavori o EPC è inventata.

Evidenze precedenti preservate: indice **37272974422**, acquisizione PDF **37274256818**, replay corretto **37276204735**, collector dedicato **37319711724**. Le **299 pagine** e i **cinque allegati** corretti restano distinti dai vecchi conteggi errati; dettagli in `docs/sources/dogc.md` e nei checkpoint dell'indice/documenti.

Output ordinario DOGC: `reports/dogc/index.html`, `coverage.json` e cartelle di acquisizione con PDF, pagine, documenti, eventi, metadati e liste municipali/rettifiche/esclusi. Gli eventi energetici entrano nel database e nei report ordinari.

## Altre fonti operative e limiti

Sono operativi **10 bollettini** (BOE nazionale e **9 CCAA**) e **3 collector di portali**. INE, REE e RAIPEE sono enrichment, non fonti aggiuntive di discovery.

**SABIA:** nel run corrente **1.658 pratiche inventariate e relativi dettagli**, **27 pratiche nella finestra**, **48 schede impianto**. Il perimetro datato rimane **ENTRY/CONSULT**: non sono date web né autorizzazioni desunte dallo stato corrente. Gli indici vengono riletti live; eventuali dettagli in cache conservano la data originale, sono riparsati e sottoposti a campione live forzato. Le potenze di gruppo non vengono duplicate.

**AND_PUBLIC:** catalogo live **13.636 record**, modalità **COMPLETE_ORDERED_PREFIX_SUFFIX**, **200 record sovrapposti verificati**. Il nuovo modulo `app.and_public_catalogue` controlla contratto ufficiale, conteggi prima/dopo, ordinamento, unicità, sovrapposizione e ricostruzione dai byte originali. Retry e pagine alternative hanno limiti espliciti. Il vecchio export offline da 13.633 record non era una prova di completezza del catalogo live. Restano **25 lacune originarie nei metadati**: acquisizione completa non significa metadati completi. Le date di aggiornamento non diventano pubblicazioni.

**GVA_PUBLIC:** distinto dal DOGV. Nel run corrente **536 pubblicazioni d'archivio / 27 pagine**; nella finestra **18 pubblicazioni**, di cui **14 eventi**, 3 atti solo rete e uno non pertinente. Stati **7 BLOCKED, 5 AUTHORIZED, 2 EARLY**; eventi **2 PROCEDURE_ENDED, 5 CONSTRUCTION_AUTH, 4 WITHDRAWN, 1 DENIED, 2 PUBLIC_INFO**. Conservati PDF completi; campi estratti dalle prime due pagine, senza OCR. Restano i flag di potenze multicomponente, conflitto titolo/atto e atto solo immagine. Nessuna chiusura di procedimento viene trasformata in autorizzazione o rinuncia inventata.

**BORM:** **4.815 righe** nell'indice corrente, acquisito live alle **2026-10-05T17:44:43.339490+00:00**, un tentativo. Lo snapshot è riusato esclusivamente nello stesso run/attempt **37350555017:1**, con identico hash e data originale. Errori persistenti o righe malformate non diventano risultati vuoti.

**BOCYL:** identità della singola disposizione, non della sola edizione. Restano backup e invarianti nella riparazione delle identità pregresse.

**DOG:** nella finestra corrente **20 edizioni, 786 voci degli indici, due pubblicazioni pertinenti e tre eventi/progetti**, con provenienza originale verificata. PSFV Porto Barroso: **0,99 MW**, Lugo, CONSTRUCTION_AUTH del **7 settembre 2026**; è la potenza finale dell'ampliamento, non la sola quota aggiunta. Nesa Monte Arca Norte e Sur: **20 MW ciascuno**, Pontevedra, PUBLIC_INFO del **30 settembre 2026**, riferimenti distinti **IN408A 2019/103-NT** e **IN408A 2019/104-NT**. Le durate dichiarate di 12 mesi non vengono convertite in date lavori. Confronto con l'archivio Galicia eseguito: **zero collegamenti esatti**.

## Inventari separati

**Galicia:** inventario validato dal run **37195445929**, **487 record / 50 pagine / 487 schede HTML**, 1.936 allegati indicizzati, non tutti scaricati. Non sono 487 progetti unici. BASELINE non significa nuove opportunità, NOT_SEEN non significa WITHDRAWN. Date web ignote e atti storici non vengono trasformati in pubblicazioni recenti. Collegamenti al DOG solo per documento o riferimento esatto.

**Catalunya:** modulo `app.catalunya_inventory`, launcher `aggiorna_inventario_catalogna.bat`, validato dal run **37241609997**, codice **b9e0cb7076c84743ace93c658979f20af60c07dc**. Due acquisizioni live complete e indipendenti, ricostruzione degli originali, baseline persistente e replay idempotente; **242 test in quella validazione**. Le acquisizioni originali restano **2026-10-04T22:51:50.223538+00:00** e **2026-10-04T22:51:55.947367+00:00**, senza variazioni nella seconda.

**137 righe eoliche + 358 fotovoltaiche = 495 righe comunali**, raggruppate in **434 gruppi diagnostici**, inclusi **82 record privi di riferimento mantenuti separati**. Non sono conteggi certificati di impianti unici. Potenze e superfici totali ripetute tra comuni non vengono sommate. Date del dataset/riunione ambientale non diventano pubblicazione, autorizzazione o lavori. DOGC è un collector datato indipendente: il suo completamento non cambia questi limiti dell'inventario.

Output Catalunya: `reports/catalunya_inventory/index.html`, `run_status.json`, snapshot e baseline `data/catalunya_inventory_baseline.json`. Errori non rimpiazzano la baseline valida. Dettagli e storico: `docs/sources/catalunya.md`, `docs/validation/2026-10-05-catalunya-inventory.json`.

## Sequenza di sviluppo

1. **Blocco attuale:** integrazione della PR #1 e verifica del nuovo HEAD su main; distinguere codice integrato, test passati e backfill live completato.
2. **Otto bollettini CCAA mancanti:** DOGV, BON, BOPV, BOPA, BOCANT, BOC-CAN, BOIB, BOR. Copertura corrente **9/17**; ampliamento con probe e validazione reale prima dell'abilitazione.
3. Altri portali pubblici regionali; poi PLACSP/consultazioni preliminari, IDAE e BDNS/SNPSAP, concorsi di capacità MITECO/ITJ.
4. CNMC distribuzione come contesto, non inventario progetti. Ricerca esterna EPC/BoP dopo l'estensione della discovery.

## Vincoli

Solo fonti ufficiali/gratuite; nessun aggregatore commerciale. Promotore distinto da EPC. REE è contesto rete. Scoring separato dal lifecycle. Non inventare nomi, MW, province, riferimenti, date o stato. Preservare external_id, URL, date e raw_text. I flag espongono dubbi, non correggono automaticamente i dati. Il gate strutturale non certifica la perfezione semantica di ciascun campo. Dashboard e aggregati separano MW sconosciuti, multi-provincia e potenze di gruppo non allocate.
