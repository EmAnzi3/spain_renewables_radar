# CURRENT STATE — Spain Renewables Radar

## Ultima certificazione integrata — 4 ottobre 2026

- **[Run 37220893072 — SUCCESS](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37220893072)**, codice funzionale **f4a88a6fe7a8706b5e30a52d168b93e060beaaeb**.
- Finestra completa **4 settembre–3 ottobre 2026**.
- **12 collector integrati**, 30 giorni per ciascuno; smoke live, **208 test**, controlli di identità, provenienza e replay superati.
- **221 schede progetto / 227 eventi**, contro 218/224 del precedente perimetro a undici fonti. Non sono 221 opportunità commerciali attive.
- **0 errori fonte/giorno**; quality gate **0 ERROR / 3 WARN / 110 INFO**.
- Mancanti: nome **2**, MW **58**, provincia singola **8**, expediente **41**.
- Gli 8 casi senza provincia singola sono multi-provincia: **0 province realmente irrisolte**.
- **38 province** nella vista; **618,26 MW multi-provincia** separati. I **30 MW di gruppo SABIA 20260224** non sono ripartiti né duplicati arbitrariamente.
- REE: **931 nodi**, snapshot 2026-10-01. Registro MITECO: **71.727 impianti**, acquisizione 2026-10-04, **8 match esatti** conservativi.
- Replay idempotente: nessun nuovo progetto/evento; provenienza degli eventi completa secondo i gate eseguiti.
- [Artifact 11310701073 — backfill-30d-output](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37220893072/artifacts/11310701073). Il report originale completo è `reports/validation_metrics.json` nell'artifact; una sintesi verificata è in `docs/validation/2026-10-04-twelve-source.json`.

Questa certificazione supera i run 37193300195 e 37196640080 a undici fonti, nonché il vecchio checkpoint a dieci fonti. Il pacchetto locale `spain_radar_gva_preview_55ecc9d.zip` è superato: **non applicarlo su main**. I commit successivi a f4a88a6 fino al presente checkpoint riguardano soltanto probe e documentazione, non modificano la pipeline certificata.

### Eventi per fonte

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

Il collegamento DOG–archivio ammette soltanto lo stesso documento ufficiale oppure il riferimento amministrativo esatto. Nel backfill certificato, il confronto con l'inventario è stato eseguito e ha prodotto **0 collegamenti esatti**: nessuna associazione per somiglianza di nome è stata inventata. La copertura datata ora viene dal DOG; l'archivio non viene retrodatato né trasformato in un feed recente.

## Altre fonti operative e limiti

Sono operativi **9 bollettini** (BOE nazionale e 8 CCAA), insieme a SABIA, Andalucía e Comunitat Valenciana. INE, REE e RAIPEE sono enrichment, non ulteriori collector di discovery.

**SABIA**: 1.659 pratiche inventariate e dettagli acquisiti, cinque tipi (FTV 770, EOL 433, EOM 74, HIB 343, ALM 39), senza filtro di stato. Nella finestra, 31 pratiche producono 53 schede impianto. Milestone datati **ENTRY/CONSULT** soltanto: non sono date web né nuove autorizzazioni dedotte dall'etichetta corrente. Le potenze dei gruppi non vengono duplicate. Gli indici vengono verificati live; i dettagli in cache conservano data originale e vengono riparsati, con campione live forzato.

**AND_PUBLIC**: 13.633 record nell'archivio; **25 lacune nei metadati della fonte**, conservate e visibili nel report. Acquisizione valida non significa metadati completi. Le richieste non diventano autorizzazioni leggendo allegati storici. Trasporto con retry limitati, evidenza delle risposte parziali e verifica del solo redirect ufficiale osservato.

**GVA_PUBLIC: attivo**, indipendente dal DOGV. Validazione dedicata **37192271844**, successivamente inclusa nelle certificazioni integrate. Archivio di **533 pubblicazioni/27 pagine**; nella finestra **22 pubblicazioni**, di cui **18 eventi**, 3 atti solo rete e 1 non pertinente. Stati: **11 BLOCKED, 5 AUTHORIZED, 2 EARLY**. Decisioni: 6 PROCEDURE_ENDED, 5 CONSTRUCTION_AUTH, 4 WITHDRAWN, 1 DENIED, 2 PUBLIC_INFO. Le chiusure di procedimento non sono rinunce o autorizzazioni inventate.

GVA conserva i PDF originali; i campi sono estratti dalle **prime due pagine** degli atti principali, senza OCR. Allegati tecnici indicizzati, non tutti acquisiti. Tre flag preservati: potenze multi-componente non sommate, contrasto di potenza tra titolo/atto, atto solo immagine. Nessuna potenza scelta arbitrariamente in presenza di conflitto. Il DOGV resta non implementato: **GVA_PUBLIC non equivale a DOGV**.

**BORM**: 4.794 righe nell'indice ufficiale; acquisizione live unica nel run/attempt, riutilizzata nel medesimo backfill conservando bytes, hash e data. Nel run certificato: **2026-10-04T17:34:22.229758+00:00**, un tentativo. Durata massima snapshot un'ora, nessun riutilizzo da run precedenti. Errori persistenti, HTML invece di JSON o righe malformate non diventano risultati vuoti.

**BOCYL**: ID della singola disposizione, non della sola edizione; recuperati atti prima collassati. Riparazione delle identità pregresse con backup e invarianti sui contenuti originali.

## Lavoro corrente — Catalunya

**Probe degli inventari ufficiali completato**, non collector attivo. Run **37221339629 — SUCCESS**: dataset eolico `dh5g-4nit` **137 righe**, fotovoltaico `ggx8-jkp4` **358 righe**. Acquisiti gli snapshot completi; conteggi e versione riconciliati prima/dopo. Originali e audit nell'artifact `catalunya-public-probe-output` **11310348543**. Dettagli in `docs/sources/catalunya.md`.

Righe per comune non equivalgono a impianti unici: 14 gruppi eolici e 28 FV hanno più righe; esistono potenze zero sulle righe secondarie. Un riferimento FV è usato per nomi differenti. Le righe in servizio non sono nuovi cantieri. `data_pon_ncia` è la data della riunione ambientale, non la pubblicazione o l'autorizzazione. Nessun record è stato inserito nel radar sulla base della data di aggiornamento del dataset.

**DOGC:** probe della navigazione pubblica **37221624700 — SUCCESS**, codice **adf38e1386bb91e73748b8403bf26a06e5266a40**: homepage e sei asset JavaScript ufficiali acquisiti. Individuati i percorsi pubblici di calendario, ricerca e sommario. **Nessuna risposta del servizio di ricerca/calendario ancora validata, nessun backfill DOGC e nessun collector DOGC dichiarato implementato.** Checkpoint in `docs/sources/dogc.md`.

Prossimo blocco: acquisizione ripetibile dell'inventario Catalunya con identità e comuni conservati, insieme alla verifica del percorso datato DOGC. Le due evidenze restano distinte finché non esiste un collegamento ufficiale e deterministico.

## Sequenza approvata

1. SABIA integrato, nei limiti dei milestone dichiarati.
2. Portali regionali energia/información pública: Andalucía e GVA operativi; Galicia inventariata e DOG datato integrato; Catalunya in lavorazione; altri da acquisire e validare.
3. **Nove bollettini autonomici ancora mancanti:** DOGC, DOGV, BON, BOPV, BOPA, BOCANT, BOC-CAN, BOIB, BOR. Copertura bollettini CCAA: **8/17**.
4. PLACSP e consultazioni preliminari.
5. IDAE e BDNS/SNPSAP.
6. Concorsi/assegnazioni di capacità MITECO/ITJ.
7. CNMC distribuzione come contesto, non inventario progetti.
8. Ricerca esterna EPC/BoP dopo l'estensione delle fonti di discovery.

## Vincoli

Solo fonti ufficiali/gratuite; nessun aggregatore commerciale. Owner/promotore distinto da EPC. REE è contesto rete. Scoring separato dal lifecycle. Mai inventare nomi, MW, provincia, expediente, date o stato. Preservare external_id, URL, date e raw_text. I flag espongono dubbi, non correggono automaticamente i dati. Il gate strutturale non certifica la perfezione semantica di ciascun campo. Il layer EPC/BoP rimane presente ma non inventa contractor; nel run certificato non risultano evidenze esplicite. Dashboard e aggregati separano MW sconosciuti, multi-provincia e potenze di gruppo non allocate.
