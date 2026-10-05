# DOGC — collector datato, originali e classificazione verificati

## Stato al 5 ottobre 2026

**DOGC è implementato e incluso nei 13 collector ordinari.** La classificazione semantica, il collector dedicato e il backfill integrato sono stati completati. La prova integrata verificata è il **[run 37350555017 — SUCCESS](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37350555017)**, codice **`ca598cc0f1e685652c6af58c83c85f6186fafd9e`**, eseguito sul branch `fix/dogc-index-reconciliation`.

Lo stato del merge e delle prove sul nuovo HEAD è registrato nella **[PR #1](https://github.com/EmAnzi3/spain_renewables_radar/pull/1)**. La prova di branch non viene presentata come una riesecuzione post-merge. Questo documento supera il precedente stato “solo indice/PDF, classificazione da completare”. Il modulo inventario Catalunya resta distinto.

| Livello | Risultato verificato |
|---|---|
| Finestra integrata | 5 settembre–4 ottobre 2026, 30 giorni, zero errori fonte/giorno |
| Indice | 1.525 disposizioni |
| PDF candidati | 48 documenti, 299 pagine |
| Eventi energetici | 33 eventi / 33 chiavi di progetto DOGC |
| Categorie separate | 11 lead municipali, una rettifica, tre atti fuori ambito |
| Geografia integrata | 31 RESOLVED, 2 MULTI_PROVINCE |
| Potenza scalare assente | 11 eventi: 6 conflitti, 3 multicomponente, 2 senza potenza univoca |
| Verifiche | integrità originali, replay PDF/semantico esatto, campi proiettati, geografia e idempotenza superati |

Checkpoint integrato: `docs/validation/2026-10-05-thirteen-source.json`. Metriche e originali completi sono nell'artifact **11363027158**, **85.228.446 byte**, SHA256 **`433b176408cd12c657139cbe06f3578f1377f4744c40124195b72132728eb7b2`**, verificato contro i byte scaricati.

## Percorso ufficiale e indice

Il sito `dogc.gencat.cat` espone negli asset ufficiali i servizi di `portaldogc.gencat.cat`. Il percorso verificato usa:

- `/eadop-rest/api/dogc/calendarDOGC`: calendario;
- `/eadop-rest/api/dogc/summaryDOGC`: sommari delle edizioni e allegati;
- `/eadop-rest/api/dogc/searchDOGC`: ricerca per data di pubblicazione;
- `/utilsEADOP/AppJava/PdfProviderServlet`: originali indicati nei sommari, con controllo del redirect HTTPS ufficiale verso `/utilsEADOP/PDF/<edizione>/<id>.pdf`.

Domini, identificativi e destinazioni vengono controllati; i percorsi PDF non sono indovinati. TLS conserva verifica di certificato/nome host, minimo TLS 1.2 e livello di sicurezza 2. Errori permanenti, dinieghi, risposte parziali e redirect estranei non diventano acquisizioni valide.

La precedente paginazione mensile ripeteva sette documenti; la causa interna del servizio non è stata accertata. La riconciliazione usa giorni disgiunti e una risposta completa per giorno, con limite esplicito 1.000: risultato troncato, limite ignorato, identità ripetuta o conteggio eccessivo fanno fallire il controllo, non vengono mascherati scartando duplicati.

Il run storico dell'indice **37272974422**, codice **33d69a0353d6db0572ece36fc5606fcd907bdeda**, ha verificato due acquisizioni live complete: **30 giorni, 20 edizioni principali, cinque allegati, 10 giorni senza edizione**, confrontando ID, date e titoli tra ricerche e sommari e riconciliando il totale mensile. Zero omissioni o conflitti sostanziali; **385 varianti tipografiche** preservate senza normalizzare via numeri, accenti o termini amministrativi.

Gli allegati corretti sono **9747A, 9748A, 9751A, 9757A, 9765A**. Il precedente conteggio di tre era errato. Evidenza storica: `docs/validation/2026-10-05-dogc-daily-index.json`.

## PDF e provenienza

Gli originali conservano URL iniziale, redirect, destinazione finale, hash, byte e data reale di acquisizione. Tutte le pagine sono estratte senza OCR. `scripts.dogc_pdf_headers` verifica la testata ufficiale completa di ogni pagina, CVE, data, edizione, numero pagina e totale; una data storica nel corpo non sostituisce la testata.

L'acquisizione storica **37274256818** fu seguita dal replay corretto **37276204735**, codice **f123ed5ba484a1188172a9c8b7b13e9fa605d0d0**: **48/48 documenti e 299/299 intestazioni**, hash e testo ricostruiti esattamente, nessuna pagina senza testo, zero nuovi download e date originali conservate. Il riepilogo intermedio di **218 pagine era errato**: i PDF contengono 299 pagine. L'audit originale cercava intestazioni in una porzione troppo limitata del testo estratto; non è stato riscritto per nascondere il problema.

L'artifact corretto **11330421970** ha SHA256 **`10d5828a9aef609a599b58eb552fb441eaeb42fffed261b74ec10692a0c57191`**. La discrepanza nei metadati esterni dello ZIP originario resta documentata; non è confusa con gli hash dei singoli PDF, verificati. Il confronto locale con una diversa versione pypdf che mostrava spaziature diverse non fu dichiarato replay esatto. Storia e discrepanze: `docs/validation/2026-10-05-dogc-document-bodies.json`.

## Semantica e proiezione nel radar

La validazione dedicata del collector **37319711724** ha preceduto quella integrata **37350555017**. I **48 candidati non sono 48 progetti**. Nel risultato integrato producono:

| Evento energetico | Numero |
|---|---:|
| PUBLIC_INFO | 13 |
| ENVIRONMENTAL_SCREENING | 10 |
| DIA | 1 |
| CONSTRUCTION_AUTH | 8 |
| PUBLIC_UTILITY | 1 |

Stati derivati: **EARLY 13, PERMITTING 11, AUTHORIZED 9**. I lead municipali restano separati: un'approvazione locale non è un permesso energetico. Le rettifiche non generano un impianto nuovo. Richiesta, screening, decisione ambientale e concessione non sono intercambiabili; la sola parola “autorizzazione” non prova una concessione.

Quantità, riferimenti e decisioni conservano evidenza delle pagine. Nessuna somma arbitraria tra impianti/componenti o tra MW, MWp/MWn, MWh e potenza di accesso. Le **sei identità con conflitto di potenza** restano **1053901, 1054244, 1054255, 1054269, 1054291, 1054428**. Non si seleziona un numero per riempire il campo.

La revisione semantica congelata copre **48 casi documento, 12 casi quantità e quattro casi riferimenti**. Il gate integrato ricostruisce la semantica dagli originali e verifica tutti i campi proiettati, provenienza, identità e replay idempotente. La proiezione geografica conserva i comuni originari: **31 casi risolti e due multi-provincia**, senza duplicazione dei MW provinciali. I risultati geografici meno completi della precedente prova isolata restano storici, non vengono attribuiti alla prova integrata.

## Output e limiti residui

Il collector `app.collectors.dogc` è richiamato dal comando ordinario; non serve un secondo launcher. Output: `reports/dogc/index.html`, `coverage.json`, cartelle di acquisizione con `documents.json`, `projected_events.json`, `event_metadata.json`, originali PDF/pagine e liste `municipal_leads.json`, `corrections.json`, `excluded.json`, `unresolved.json`. Solo gli eventi energetici entrano nel database e nella dashboard ordinari.

**Rimangono 11 eventi senza MW scalari determinabili.** Nessuna data lavori o EPC è dedotta. AUTHORIZED è uno stato amministrativo derivato dagli atti acquisiti, non la prova che un cantiere sia iniziato. La validazione riguarda la finestra e i controlli dichiarati, non una garanzia di completezza assoluta o futura del DOGC.

L'inventario Catalunya rimane un'acquisizione indipendente senza eventi datati. Collegarlo al radar richiede documento ufficiale o riferimento esatto e validazione separata; non è stato introdotto un collegamento automatico per somiglianza di nome.
