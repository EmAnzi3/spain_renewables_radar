# CURRENT STATE — Spain Renewables Radar

Checkpoint **6 ottobre 2026, Europe/Rome**. La **PR #2 è integrata in main**, commit funzionale **dc4630627ac3043e70bb644a27ce0942ad0580f4**. Il successivo `74635d9a5070dd07f9cb186b6fe6a43304f7008b` aggiunge soltanto un controllo di connettività ARM64. **Classificazione BOPV completata sul perimetro verificato; disponibilità live GVA ancora bloccata.** Non dichiarare risolta la seconda perché sono verdi i test del codice.

## Esiti verificati

| Blocco | Esito |
|---|---|
| Suite locale completa | **586 test superati**, compresi 34 nuovi casi BOPV e 22 casi GVA catalogo/sessione/preflight |
| Test del commit di merge | **37430217747 — SUCCESS** |
| Test della revisione con probe ARM64 | **37430471783 — SUCCESS** |
| BOPV classificazione su branch | **37428902802 — SUCCESS**, artifact scaricato e riprodotto localmente |
| BOPV classificazione post-merge | **37430217754 — SUCCESS** |
| GVA dedicato post-merge | **37430217761 — FAILURE** |
| Backfill post-merge | **37430217829 — FAILURE nel preflight GVA**; altre acquisizioni e certificazione integrata SKIPPED |
| GVA accessi ufficiali alternativi | **37428381186 — FAILURE**; entrambi in timeout prima della risposta HTTP |
| GVA runner ARM64 | **37430471860 — FAILURE**, stessa destinazione e stesso ConnectTimeout |
| DOCM/Almagro dedicato | **37420987930 — SUCCESS**, correzione preservata |
| Ultimo backfill integrato completato | **37406054339 — SUCCESS**, precedente alla correzione Almagro |

Checkpoint di questo blocco: `docs/validation/2026-10-06-gva-bopv-completion.json`. I nuovi controlli non sono una nuova certificazione integrata riuscita.

## GVA — robustezza client pubblicata, disponibilità non certificata

Il codice operativo contiene:

- **sessione anonima persistente e connessioni riutilizzate**, intervallo minimo di 0,75 secondi fra richieste; reset di connessioni/cookie solo dopo errori transitori;
- **tre tentativi completi al massimo**, senza retry annidati. Dinieghi, HTTP 400/401/403/404/429, errori di certificato e dati malformati non vengono trasformati in retry o risultati validi;
- **un catalogo completo riutilizzabile solo nello stesso run/attempt**, entro un'ora, dopo rilettura di tutti gli originali, verifica di hash, date delle singole ricevute, numero/ordine delle pagine e identità univoche; nuova verifica live della prima e dell'ultima pagina;
- un errore live non autorizza il recupero di dati vecchi; una modifica delle estremità o una cache non valida richiede un nuovo catalogo completo. Le pagine intermedie restano lo snapshot originale dello stesso run, non una nuova acquisizione live attribuita retroattivamente;
- **job GVA/backfill serializzati** nella stessa concurrency group, per non eseguire contemporaneamente due scansioni;
- **preflight GVA prima delle altre dodici fonti**, con ricevuta esplicita. Se il catalogo non è disponibile il run fallisce subito, senza una scansione parziale presentata come completa.

Moduli: `app/gva_transport.py`, `app/gva_catalogue.py`, `app/gva_preflight.py`. Nessuna modifica all'interpretazione dei progetti GVA. Il launcher ordinario resta invariato; il preflight anticipato è nel workflow di certificazione, non una nuova fonte.

### Guasto live ancora osservato

I precedenti problemi erano HTTP 400 e timeout sulla pagina 15. Nei controlli di questo blocco il guasto è precedente: **ConnectTimeout durante l'apertura della connessione, zero byte e nessuna risposta HTTP**. Il probe con timeout connessione di 20 secondi ha verificato `cindi.gva.es` e `mediambient.gva.es`: entrambi risolvono **195.77.19.35** e non rispondono dai runner provati. Non è dimostrato un disservizio globale, un blocco geografico o una causa interna del server.

Il run post-merge **37430217829** si è fermato nel nuovo preflight: tre tentativi, nessun dato ricevuto, nessun evento creato. Artifact **11397050969**, **1.182.596 byte**, SHA256 **ae58dfc5684a8ddf55789d7dc89b973b1bd6abac2f77f9de89e7d2dcbb08296e**, scaricato e verificato. Ricevuta `reports/gva_public/preflight.json`; nessun download delle altre dodici fonti.

Un confronto su runner standard **ARM64** ha mantenuto endpoint, TLS e budget identici: **37430471860** termina con lo stesso errore, non corregge la disponibilità. Artifact **11396303764**, **3.038 byte**, SHA256 **9cf5fd6a1b5e4ae2cbf66baaf433fe71aadc0a7f356fcc7b15d3a7395922f2a4**, scaricato e verificato. Il workflow ordinario non è stato spostato su ARM64.

**Blocco residuo:** recuperare la raggiungibilità dell'endpoint dai runner o identificare e validare un'altra pubblicazione ufficiale equivalente. Non continuare a modificare il parser o rilanciare senza limiti una connessione che non riceve risposte. Non saltare GVA, non usare proxy/credenziali o vecchi record per simulare il successo.

## BOPV — classificazione completata, collector ancora separato

Indice ufficiale **37420987792 — SUCCESS**: **306 disposizioni**, ricerca su **31 pagine**, **21 edizioni**, **30 giorni**, inclusi **9 senza edizione**; zero omissioni o conflitti di identità/titolo. Gli originali e le date dei cinque avvisi sono stati verificati indipendentemente.

Il modulo **`app/bopv_semantics.py`** e **`scripts/validate_bopv_semantics.py`** ricostruiscono l'indice dagli originali, classificano tutti i candidati e confrontano ogni impianto con cinque casi revisionati. Ogni valore conserva il paragrafo e l'intervallo esatto della fonte. **34 nuove regressioni** coprono domande/concessioni, DIA, impianti multipli, riferimenti condivisi/estranei, MW/kVA/MWh, geografia e soggetti.

**Classificazione validata: 37428902802**, codice **81bbcd0ccf74b953e1eb4ee28c7da39ad6ab2484**, ripetuta positivamente su main nel run **37430217754**. Artifact della prima prova **11396013105**, **177.904 byte**, SHA256 **8dc9a0133c708c6cf3bfca39f065790683f05069b54e3556197d798a09999e52**, scaricato, ricalcolato e confrontato campo per campo con una ricostruzione locale dagli HTML originali. Non sono nuove acquisizioni retrodatate: la finestra rimane **6 settembre–5 ottobre 2026**.

| Impianto | Tecnologia | MW espliciti | Localizzazione di impianto | Evento/stato |
|---|---|---:|---|---|
| Hernani I | WIND | 4,99 | Villabona, Gipuzkoa | PUBLIC_INFO / EARLY |
| Hernani II | WIND | 4,99 | Villabona, Gipuzkoa | PUBLIC_INFO / EARLY |
| Regina Solar | PV | 10,12 | Vitoria-Gasteiz e Arratzua-Ubarrundia, Álava | PUBLIC_INFO / EARLY |
| Nova Solar | PV | 1 | Vitoria-Gasteiz, Álava | PUBLIC_INFO / EARLY |
| Pe Pando | WIND | 30 | Ayala e Okondo, Álava | PUBLIC_INFO / EARLY |
| Mendi | WIND | 31,2 | Amurrio e Ayala, Álava | DIA / PERMITTING |

**Sei impianti energetici, non cinque e non sette.** Il settimo soggetto estratto, **Coalsema**, è un progetto industriale ibrido per autoconsumo, conservato come **SELF_CONSUMPTION_LEAD** separato. Il totale MW resta vuoto: potenza apparente FV, potenza attiva PCS, energia per contenitore e cogenerazione esistente non vengono sommati. Le quantità originali sono comunque disponibili.

Hernani I e II condividono il dossier **20-GE-Y-2025-00004** ma hanno proprietari distinti; l'applicant del gruppo non viene assegnato come owner a entrambi. Regina e Nova conservano i propri dossier distinti, senza prendere quelli degli impianti che condividono l'evacuazione. **Pando e Mendi non hanno un expediente individuale inequivocabile nel testo disponibile**: il campo resta vuoto e l'identità è provvisoria. La categoria GE–Y non diventa un codice di pratica inventato.

Mendi ha una DIA, non un'autorizzazione alla costruzione. Nessuna data lavori o EPC viene dedotta. Le tabelle disponibili soltanto nel PDF sono segnalate e non interpretate dall'HTML.

**BOPV resta `implemented=false`, nessun evento BOPV è scritto nel database ordinario.** La richiesta di classificazione è chiusa sul perimetro verificato; l'abilitazione della quattordicesima fonte richiede ancora collector live, persistenza delle identità provvisorie, smoke, backfill e controlli integrati. Output del classificatore: `index.html`, `assets.csv`, `classified_documents.json`, `originals/` e `validation_metrics.json` nell'artifact. Metodo: `docs/sources/bopv.md`.

## Almagro — correzione preservata

DOCM-2026-7037, pubblicazione **5 ottobre 2026**: **BESS Almagro I, 7,2 MW, Almagro/Ciudad Real, Castilla-La Mancha**, expediente **13270209226**, PUBLIC_INFO/EARLY. I 7,4 MW del FV esistente, 14,6 MW complessivi dopo ibridazione, accesso, kVA/MVA e MWh restano separati.

La migrazione dei valori precedenti resta hash-locked, con backup, transazione e rollback in caso di difformità. È stata provata su una copia del database precedente: solo nome, tecnologia, potenza e provincia di Almagro modificati; identità, testo, URL, date e lifecycle immutati; replay senza ulteriori correzioni.

Prova DOCM **37420987930 — SUCCESS**, **18 eventi / 18 progetti, 30 giorni, zero errori fonte/giorno e strutturali**. Non è una certificazione delle tredici fonti. Evidenze: `docs/validation/2026-10-06-almagro-bopv.json`, `docs/sources/docm-storage.md`.

## Ultimo dataset integrato completo, storico

**37406054339 — SUCCESS**, codice **88201b5a2e2f5b35c39ac028d44c4d3e155a3391**, **6 settembre–5 ottobre 2026**: **256 schede / 262 eventi**, 13 fonti × 30 giorni, zero errori fonte/giorno, qualità **0 ERROR / 9 WARN / 184 INFO**. Mancanti: nome2, MW69, provincia singola10, expediente39. La geografia di quel dataset contiene nove multi-provincia e Almagro ancora irrisolto.

**L'artifact storico conserva il vecchio valore Almagro.** Non modificarne retroattivamente i numeri per descrivere il codice corretto. Le sette BESS Begues sono distinte e Gandia Hive è DENIED/BLOCKED. Artifact11388095924,91.685.094byte,SHA256 fae2b7a9b3a15d502bc04ab1b81110b74d6fafceac70c4de5802e61e632f08d6. Storico dettagliato nella revisione precedente di questo documento e nei checkpoint di validazione.

## Perimetro e prossime attività

13 collector nel codice: **BOE, BOCYL, BOA, BOJA, DOCM, DOE, BORM, BOCM, DOG, DOGC, AND_PUBLIC, GVA_PUBLIC, MITECO_SABIA**. GVA è implementato ma attualmente non acquisibile dai runner verificati. Bollettini CCAA **9/17**. Mancanti **DOGV, BON, BOPV, BOPA, BOCANT, BOC-CAN, BOIB, BOR**. INE, REE e RAIPEE sono enrichment, non nuove fonti di discovery.

Prossimi blocchi: disponibilità GVA e nuova prova integrata; collector BOPV basato sulla classificazione validata; altre fonti regionali, PLACSP, IDAE/BDNS, capacità MITECO/ITJ e contesto CNMC. EPC/BoP esterno resta successivo alla discovery. Gli inventari Catalunya/Galicia restano separati, così come milestone SABIA, dati REE e potenze multi-provincia/non allocate.

BAT ordinario **aggiorna_radar_spagna.bat**, ultimi sette giorni, invariato. I commit remoti non aggiornano il database sul PC e non pubblicano da soli una dashboard. Solo fonti ufficiali/gratuite; nessun aggregatore commerciale. Preservare external_id, URL, raw_text, date e ruoli; non abbassare i gate né scambiare un successo del test per disponibilità della fonte.
