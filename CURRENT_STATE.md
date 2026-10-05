# CURRENT STATE — Spain Renewables Radar

Aggiornamento del checkpoint: **5 ottobre 2026, Europe/Rome**. Le date UTC originali delle acquisizioni rimangono conservate. Il lavoro DOGC descritto sotto è sul branch **`fix/dogc-index-reconciliation`**, **PR #1 OPEN/DRAFT, non mergiata**; non modifica la pipeline di produzione.

## Ultima certificazione integrata verificata — 4 ottobre 2026

- **[Run 37220893072 — SUCCESS](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37220893072)**, codice funzionale **f4a88a6fe7a8706b5e30a52d168b93e060beaaeb**.
- Finestra completa **4 settembre–3 ottobre 2026**.
- **12 collector integrati**, 30 giorni per ciascuno; smoke live, **208 test nel run certificato**, controlli di identità, provenienza e replay superati.
- **221 schede progetto / 227 eventi**, contro 218/224 del precedente perimetro a undici fonti. Non sono 221 opportunità commerciali attive.
- **0 errori fonte/giorno**; quality gate **0 ERROR / 3 WARN / 110 INFO**.
- Mancanti: nome **2**, MW **58**, provincia singola **8**, expediente **41**.
- Gli 8 casi senza provincia singola sono multi-provincia: **0 province realmente irrisolte**.
- **38 province** nella vista; **618,26 MW multi-provincia** separati. I **30 MW di gruppo SABIA 20260224** non sono ripartiti né duplicati arbitrariamente.
- REE: **931 nodi**, snapshot 2026-10-01. Registro MITECO: **71.727 impianti**, acquisizione 2026-10-04, **8 match esatti** conservativi.
- Replay idempotente: nessun nuovo progetto/evento; provenienza degli eventi completa secondo i gate eseguiti.
- [Artifact 11310701073 — backfill-30d-output](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37220893072/artifacts/11310701073). Il report originale completo è `reports/validation_metrics.json` nell'artifact; una sintesi verificata è in `docs/validation/2026-10-04-twelve-source.json`.

Questa certificazione supera i run 37193300195 e 37196640080 a undici fonti, nonché il vecchio checkpoint a dieci fonti. Il pacchetto locale `spain_radar_gva_preview_55ecc9d.zip` è superato: **non applicarlo su main**.

Successivamente sono stati aggiunti l'inventario Catalunya separato, il relativo launcher, moduli DOGC di acquisizione/verifica, test e documentazione. **I collector esistenti, il parser comune e la pipeline ordinaria non sono stati modificati da questo blocco.** L'inventario e i candidati DOGC non aggiungono un tredicesimo collector operativo. I test successivi e i replay degli originali non sostituiscono una certificazione live integrata. Il run completo 37241609962 è stato cancellato durante lo smoke: non è una nuova certificazione e non aggiorna i conteggi sopra riportati.

### Eventi per fonte nel run integrato certificato

| Fonte | Eventi |
|---|---:|
| BOE | 41 |
| BOCYL | 36 |
| BOA | 21 |
| BOJA | 7 |
| DOCM | 17 |
| DOE | 8 |
| BORM | 11 |
| BOCM | 4 |
| DOG | 3 |
| AND_PUBLIC | 8 |
| GVA_PUBLIC | 18 |
| MITECO_SABIA | 53 |

## Galicia — DOG operativo e validato

**DOG è il dodicesimo collector**, abilitato nel comando ordinario e nel registry. Fonte: calendario ufficiale mensile, indici delle edizioni e tutte le sezioni spagnole collegate, poi testo HTML originale degli avvisi pertinenti. Le date sono verificate sull'edizione e sul documento, non ricavate dalla data dell'atto o dal giorno del download.

- Probe ufficiale **37196236454 — SUCCESS**.
- Collector e test: commit **b91c620d64c2bf490e5dc560e6b924dfde379d08**.
- Validazione dedicata **37220564261 — SUCCESS**, inclusi smoke e backfill di 30 giorni.
- Integrazione: commit **f4a88a6fe7a8706b5e30a52d168b93e060beaaeb**, certificata nel run completo **37220893072**.
- **21 edizioni, 817 voci degli indici, 2 pubblicazioni pertinenti, 3 eventi/schede progetto**; nessun campo principale mancante per questi tre progetti, nessun errore strutturale e nessun candidato irrisolto nella finestra verificata.

| Progetto | Tecnologia | MW della fonte | Provincia | Pubblicazione | Evento |
|---|---|---:|---|---|---|
| PSFV Porto Barroso | FV | 0,99 | Lugo | 2026-09-07 | CONSTRUCTION_AUTH |
| Nesa Monte Arca Norte | Eolico | 20 | Pontevedra | 2026-09-30 | PUBLIC_INFO |
| Nesa Monte Arca Sur | Eolico | 20 | Pontevedra | 2026-09-30 | PUBLIC_INFO |

**Porto Barroso:** autorizzazione del progetto di ampliamento; 0,99 MW è la potenza finale dell'impianto, non la nuova potenza aggiuntiva. Flag INFO `EXPANSION_CAPACITY_IS_RESULTING_PLANT_NOT_INCREMENT` conservato.

**Monte Arca:** due parchi distinti nella stessa pubblicazione, riferimenti **IN408A 2019/103-NT** e **IN408A 2019/104-NT**, promotori e sezioni del testo distinti. Le richieste di autorizzazione restano PUBLIC_INFO/EARLY, non diventano autorizzazioni concesse. Il termine dichiarato è **12 mesi per ciascun parco**; la durata e il testo originale sono conservati, mentre le date di inizio/fine lavori restano vuote. Le durate specifiche delle infrastrutture di evacuazione non sono confuse con il periodo del parco.

Output operativi: `reports/dog/coverage.json`, `reports/dog/raw/`, `reports/dog/galicia_links.json`; i progetti entrano nei report e nella dashboard ordinari. Le evidenze sono separate in `regional_public_metadata`. Il gate integrato ricostruisce i campi dagli HTML originali e li confronta con database e metadati, controllando hash, identità, date, conteggi e replay.

### Inventario storico Galicia, sempre separato

`app.galicia_archive` è validato come inventario nel run **37195445929**: **487 record/50 pagine/487 schede HTML**, suddivisi in 298 consultazioni, 123 autorizzazioni, 66 documentazione ambientale; **1.936 allegati indicizzati**, non scaricati. Non sono 487 progetti unici. Le date web restano ignote, la data dell'atto più recente riconosciuta è 2026-04-20. BASELINE non significa nuove opportunità e NOT_SEEN non significa WITHDRAWN.

Il collegamento DOG–archivio ammette soltanto lo stesso documento ufficiale oppure il riferimento amministrativo esatto. Nel backfill certificato, il confronto con l'inventario è stato eseguito e ha prodotto **0 collegamenti esatti**: nessuna associazione per somiglianza di nome è stata inventata. La copertura datata viene dal DOG; l'archivio non viene retrodatato né trasformato in un feed recente.

## Altre fonti operative e limiti

Sono operativi **9 bollettini** (BOE nazionale e 8 CCAA), insieme a SABIA, Andalucía e Comunitat Valenciana. INE, REE e RAIPEE sono enrichment, non ulteriori collector di discovery.

**SABIA**: 1.659 pratiche inventariate e dettagli acquisiti, cinque tipi (FTV 770, EOL 433, EOM 74, HIB 343, ALM 39), senza filtro di stato. Nella finestra, 31 pratiche producono 53 schede impianto. Milestone datati **ENTRY/CONSULT** soltanto: non sono date web né nuove autorizzazioni dedotte dall'etichetta corrente. Le potenze dei gruppi non vengono duplicate. Gli indici vengono verificati live; i dettagli in cache conservano data originale e vengono riparsati, con campione live forzato.

**AND_PUBLIC**: 13.633 record nell'archivio; **25 lacune nei metadati della fonte**, conservate e visibili nel report. Acquisizione valida non significa metadati completi. Le richieste non diventano autorizzazioni leggendo allegati storici. Trasporto con retry limitati, evidenza delle risposte parziali e verifica del solo redirect ufficiale osservato.

**GVA_PUBLIC: attivo**, indipendente dal DOGV. Validazione dedicata **37192271844**, successivamente inclusa nelle certificazioni integrate. Archivio di **533 pubblicazioni/27 pagine**; nella finestra **22 pubblicazioni**, di cui **18 eventi**, 3 atti solo rete e 1 non pertinente. Stati: **11 BLOCKED, 5 AUTHORIZED, 2 EARLY**. Decisioni: 6 PROCEDURE_ENDED, 5 CONSTRUCTION_AUTH, 4 WITHDRAWN, 1 DENIED, 2 PUBLIC_INFO. Le chiusure di procedimento non sono rinunce o autorizzazioni inventate.

GVA conserva i PDF originali; i campi sono estratti dalle **prime due pagine** degli atti principali, senza OCR. Allegati tecnici indicizzati, non tutti acquisiti. Tre flag preservati: potenze multi-componente non sommate, contrasto di potenza tra titolo/atto, atto solo immagine. Nessuna potenza scelta arbitrariamente in presenza di conflitto. Il DOGV resta non implementato: **GVA_PUBLIC non equivale a DOGV**.

**BORM**: 4.794 righe nell'indice ufficiale; acquisizione live unica nel run/attempt, riutilizzata nel medesimo backfill conservando bytes, hash e data. Nel run certificato: **2026-10-04T17:34:22.229758+00:00**, un tentativo. Durata massima snapshot un'ora, nessun riutilizzo da run precedenti. Errori persistenti, HTML invece di JSON o righe malformate non diventano risultati vuoti.

**BOCYL**: ID della singola disposizione, non della sola edizione; recuperati atti prima collassati. Riparazione delle identità pregresse con backup e invarianti sui contenuti originali.

## Catalunya — inventario implementato e validato

**[Run 37241609997 — SUCCESS](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37241609997)**, codice funzionale **b9e0cb7076c84743ace93c658979f20af60c07dc**. Sono passati **242 test**, due acquisizioni live indipendenti con pagine da 100 righe, ricostruzione dai byte originali, riconciliazione dei conteggi e delle versioni prima/dopo, baseline persistente e replay idempotente.

| Controllo | Eolico | Fotovoltaico |
|---|---:|---:|
| Righe comunali originali | 137 | 358 |
| Gruppi diagnostici complessivi | 115 | 319 |
| Gruppi con riferimento e nome esatti | 37 | 315 |
| Righe senza riferimento, mantenute separate | 78 | 4 |
| Gruppi con più righe comunali | 14 | 28 |
| Gruppi senza potenza determinabile | 28 | 0 |

**495 righe comunali e 434 gruppi diagnostici non equivalgono a 495 o 434 impianti unici.** Gli 82 record senza riferimento restano separati; un riferimento FV usato per due nomi diversi non provoca la loro fusione. Potenza, superficie totale e numero totale di aerogeneratori ripetuti non vengono sommati fra comuni. Zeri originali conservati; conflitti positivi non risolti arbitrariamente.

La prima acquisizione è BASELINE. La seconda è DELTA: **0 nuove voci osservate, 0 modifiche, 0 voci non più osservate**. Date originali UTC: `2026-10-04T22:51:50.223538+00:00` e `2026-10-04T22:51:55.947367+00:00`. I dataset della fonte risultano aggiornati al **28 settembre 2026**: questa è la data del dataset, non dei progetti.

Modulo **`app.catalunya_inventory`**; avvio Windows **`aggiorna_inventario_catalogna.bat`**. Output locale: **`reports/catalunya_inventory/index.html`**; esito dell'ultimo tentativo: `reports/catalunya_inventory/run_status.json`; baseline: `data/catalunya_inventory_baseline.json`. Ogni snapshot conserva JSON, CSV, report HTML consultabile, variazioni, metriche e originali con hash/data. Un errore di acquisizione non rimpiazza la baseline valida; gli aggiornamenti concorrenti sono bloccati.

[Artifact 11317693006 — catalunya-inventory-output](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37241609997/artifacts/11317693006), SHA256 `b9f1361f7dc9bcad1f3aa5dda633015befc26e98d0e224841b3f927ad7833ee8`. Sintesi verificata in `docs/validation/2026-10-05-catalunya-inventory.json`; metodo in `docs/sources/catalunya.md`.

**Nessun evento datato creato e nessun nuovo collector abilitato.** Stato della fonte e data della riunione ambientale non diventano una nuova autorizzazione; nessuna data di pubblicazione/lavori o EPC viene dedotta. Il probe precedente 37221339629 resta evidenza storica, superato per l'acquisizione dell'inventario dalla validazione del modulo ripetibile.

## DOGC — indice riconciliato, PDF verificati, classificazione da completare

**Indice: run 37272974422 — SUCCESS**, codice `33d69a0353d6db0572ece36fc5606fcd907bdeda`. Finestra **5 settembre–4 ottobre 2026**: **1.525 disposizioni, 30 giorni, due acquisizioni live complete, 20 edizioni principali, cinque allegati, 10 giorni senza edizione**. Confronto di ogni ID, data e titolo fra ricerche giornaliere complete e sommari, riconciliazione del totale mensile e ricostruzione dai byte originali. **Zero omissioni, avvisi aggiuntivi o conflitti sostanziali; 385 varianti tipografiche conservate separatamente.**

La paginazione mensile ripeteva sette documenti: ora viene usato un risultato completo per giorno, senza scartare duplicati per nascondere lacune. Gli allegati effettivi sono `9747A`, `9748A`, `9751A`, `9757A`, `9765A`; il riepilogo precedente che ne indicava tre era errato. Dettagli: `docs/validation/2026-10-05-dogc-daily-index.json`.

**48 PDF candidati acquisiti, 299 pagine effettive.** Acquisizione originale `37274256818`, codice `d63e2f5f3333a890e02bb55f00f42c8ceb8c5891`. Il controllo diretto dell'archivio ha smentito il riepilogo intermedio di 218 pagine: l'audit originale riconosceva solo due intestazioni perché l'estrattore colloca molte testate dopo il corpo e può inserire spazi nella data. L'audit e i file originari sono conservati immutati.

**Replay corretto: run 37276204735 — SUCCESS**, codice funzionale `f123ed5ba484a1188172a9c8b7b13e9fa605d0d0`. Ricostruiti indice, testo e numero pagine dagli originali; verificati **48/48 documenti e 299/299 intestazioni**, con data, edizione, posizione della pagina e stesso CVE all'interno di ciascun documento. Hash e provenienza coincidono, nessuna pagina è priva di testo, il confronto esatto dei testi è passato. **Zero nuovi download dalla fonte e date originali preservate.** Suite di regressione verde; 12 nuove regressioni sulla disposizione delle intestazioni.

Il nuovo artifact **11330421970 — `dogc-original-replay-output`** è stato scaricato e confrontato con il digest API, SHA256 `10d5828a9aef609a599b58eb552fb441eaeb42fffed261b74ec10692a0c57191`. La discrepanza nei metadati esterni dello ZIP di acquisizione originario rimane documentata, senza confonderla con i controlli sui singoli PDF: i loro hash coincidono con il replay corretto. Checkpoint completo: `docs/validation/2026-10-05-dogc-document-bodies.json`; metodo e ripartenza: `docs/sources/dogc.md`.

**Questo non abilita DOGC come tredicesimo collector.** I 48 titoli sono candidati ampi, non impianti o autorizzazioni validate. Restano classificazione della pertinenza, lettura del dispositivo con evidenza della pagina, separazione per impianto/componente, test semantici e certificazione integrata. Nessun MW, stato autorizzativo, data di cantiere o EPC è stato dedotto in questo blocco; nessun evento DOGC è stato scritto nel radar.

## Sequenza approvata

1. SABIA integrato, nei limiti dei milestone dichiarati.
2. Portali regionali energia/información pública: Andalucía e GVA operativi; Galicia inventariata e DOG datato integrato; Catalunya inventario validato, DOGC indice/PDF verificati e classificazione in preparazione; altri da acquisire e validare.
3. **Nove bollettini autonomici ancora non operativi:** DOGC, DOGV, BON, BOPV, BOPA, BOCANT, BOC-CAN, BOIB, BOR. Copertura operativa bollettini CCAA: **8/17**.
4. PLACSP e consultazioni preliminari.
5. IDAE e BDNS/SNPSAP.
6. Concorsi/assegnazioni di capacità MITECO/ITJ.
7. CNMC distribuzione come contesto, non inventario progetti.
8. Ricerca esterna EPC/BoP dopo l'estensione delle fonti di discovery.

## Vincoli

Solo fonti ufficiali/gratuite; nessun aggregatore commerciale. Owner/promotore distinto da EPC. REE è contesto rete. Scoring separato dal lifecycle. Mai inventare nomi, MW, provincia, expediente, date o stato. Preservare external_id, URL, date e raw_text. I flag espongono dubbi, non correggono automaticamente i dati. Il gate strutturale non certifica la perfezione semantica di ciascun campo. Il layer EPC/BoP rimane presente ma non inventa contractor; nel run integrato certificato non risultano evidenze esplicite. Dashboard e aggregati separano MW sconosciuti, multi-provincia e potenze di gruppo non allocate.
