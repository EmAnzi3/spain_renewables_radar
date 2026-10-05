# DOGC — indice datato e fascicolo documentale

## Stato al 5 ottobre 2026

Sviluppo isolato su `fix/dogc-index-reconciliation`, PR **#1 OPEN/DRAFT**, non integrata in `main`. **L'indice è riconciliato e i 48 PDF candidati sono acquisiti; la classificazione semantica e il collector di produzione non sono completati.** Nessun evento DOGC è stato inserito nel radar ordinario.

| Livello | Risultato verificato | Evidenza |
|---|---|---|
| Indice ufficiale | 1.525 disposizioni; 30 giorni; due acquisizioni live complete | Run `37272974422`, codice `33d69a0353d6db0572ece36fc5606fcd907bdeda` |
| Calendario/sommari | 20 edizioni principali, 5 allegati, 10 giorni senza edizione | Stesso indice, originali conservati |
| Selezione ampia per titolo | 48 avvisi candidati, non 48 impianti | `candidates.json` nell'artifact dell'indice |
| PDF originali | 48 file, **299 pagine effettive** | Acquisizione `37274256818`, codice `d63e2f5f3333a890e02bb55f00f42c8ceb8c5891` |
| Verifica corretta delle pagine | 299/299 intestazioni; testo ricostruito esattamente; hash e provenienza verificati | Replay `37276204735`, codice `f123ed5ba484a1188172a9c8b7b13e9fa605d0d0` |
| Interpretazione progetti/permessi | **Da completare** | Nessun campo o evento amministrativo creato |

Checkpoint: `docs/validation/2026-10-05-dogc-daily-index.json` e `docs/validation/2026-10-05-dogc-document-bodies.json`. Il secondo distingue l'acquisizione originaria dal controllo corretto e documenta tutte le discrepanze di verifica.

## Percorso ufficiale verificato

Il sito pubblico `dogc.gencat.cat` espone negli asset ufficiali i servizi di `portaldogc.gencat.cat`: calendario mensile, sommario dell'edizione e ricerca. Il probe `37241609987` ha acquisito risposte reali. La compatibilità TLS mantiene verifica del certificato e del nome host, TLS minimo 1.2 e livello di sicurezza 2.

Il percorso verificato usa i servizi ufficiali:

- `/eadop-rest/api/dogc/calendarDOGC` per tutti i giorni del mese;
- `/eadop-rest/api/dogc/summaryDOGC` per le edizioni e gli allegati;
- `/eadop-rest/api/dogc/searchDOGC` per la ricerca per data di pubblicazione;
- `/utilsEADOP/AppJava/PdfProviderServlet` per gli originali indicati nei sommari, seguendo solo il redirect HTTPS fornito dal portale verso `/utilsEADOP/PDF/<edizione>/<id>.pdf` nella stessa edizione.

I domini, gli identificativi e le destinazioni vengono controllati prima del contatto; non si costruiscono percorsi PDF indovinando gli identificativi. Errori permanenti, dinieghi, risposte parziali o redirect estranei non diventano acquisizioni valide.

## Indice: chiusura della riconciliazione

La paginazione della ricerca mensile aveva restituito sette documenti ripetuti nella quinta pagina. L'audit `37242571670` si era fermato correttamente; la diagnostica `37242677858` aveva confermato le ripetizioni negli originali e la corrispondenza dei parametri al codice pubblico del sito. La causa interna del servizio non è stata accertata. L'esportazione CSV proposta dal servizio è andata in timeout nel run `37242776975`; non è stata usata come prova di completezza.

Il nuovo modulo `scripts.reconcile_dogc_daily` divide la finestra **5 settembre–4 ottobre 2026** in giorni disgiunti. Per ciascun giorno richiede l'intero risultato in un'unica risposta. Il limite di 1.000 è una protezione esplicita: un conteggio superiore, un limite ignorato, un risultato troncato o un'identità ripetuta fanno fallire il controllo.

Ogni identità, data e titolo viene confrontato con il sommario dell'edizione e degli allegati, anche nei giorni festivi e nei giorni ufficialmente privi di edizione. La somma è riconciliata con il totale mensile. L'intera acquisizione è ripetuta live: **due passaggi completi, 60 risposte giornaliere, zero documenti mancanti o aggiuntivi, zero differenze sostanziali nei titoli, zero variazioni semantiche fra passaggi**. I byte originali sono ricostruiti e confrontati con gli indici elaborati.

Le 385 varianti tipografiche riguardano apostrofi/virgolette e composizione Unicode. I due titoli originali sono conservati. Non vengono rimossi accenti, maiuscole, cifre, identificativi o termini amministrativi per far coincidere testi diversi.

Gli allegati effettivi sono **9747A, 9748A, 9751A, 9757A, 9765A**. Il precedente riepilogo che ne elencava tre era errato; la correzione riguarda la documentazione, non nuove pubblicazioni o nuove date.

## PDF: verifica dai file, non dai soli log

Il modulo `scripts.acquire_dogc_bodies` ricostruisce prima l'indice certificato, verifica l'elenco dei candidati e acquisisce i relativi PDF originali, conservando URL iniziale, redirect, URL finale, hash, byte e data originale. Tutte le pagine sono estratte senza OCR. Questa operazione non interpreta richieste, decisioni, potenze o stato dei cantieri.

Il download diretto dell'artifact ha corretto un riepilogo intermedio non affidabile: i file contengono **299 pagine**, non 218. L'audit originario riconosceva solo due intestazioni perché cercava nei primi 1.200 caratteri estratti: il motore PDF colloca molte intestazioni stampate dopo il testo del documento e può inserire spazi nella data. L'originale e il suo audit non sono stati modificati.

`scripts.dogc_pdf_headers` verifica invece il blocco completo della testata ufficiale, con nome del giornale e CVE, indipendentemente dalla posizione nell'estrazione. Controlla **ogni pagina**, data, edizione, numero pagina, numero complessivo e stesso CVE all'interno del documento. Riferimenti storici nel testo non sostituiscono un'intestazione mancante. Dodici nuove regressioni coprono questi casi.

`scripts.recheck_dogc_bodies` rilegge gli originali già acquisiti. Il run **37276204735 è SUCCESS**: ricostruzione completa dell'indice, 48 hash PDF corrispondenti, **299/299 intestazioni di pagina**, 48/48 documenti, uguaglianza esatta dei testi ricostruiti, nessuna pagina senza testo. **Zero nuovi download dalla fonte e date originarie conservate.** La suite di regressione è SUCCESS sul medesimo codice.

Il nuovo artifact `dogc-original-replay-output`, ID **11330421970**, è stato scaricato e verificato localmente: SHA-256 `10d5828a9aef609a599b58eb552fb441eaeb42fffed261b74ec10692a0c57191`. Il report è `dogc_body_recheck.json` e contiene i controlli di ogni documento e pagina.

La discrepanza osservata nei metadati esterni dello ZIP originario è documentata nel checkpoint, non eliminata: per il contenuto sono stati confrontati i file PDF e i loro hash con il replay corretto. L'archivio del replay corretto coincide con il relativo digest API. Un confronto locale con una diversa versione di pypdf aveva mostrato quattro differenze di spaziatura e non era stato dichiarato replay esatto; il gate CI richiede uguaglianza esatta ed è passato senza differenze.

## Confine ancora aperto

I 48 candidati comprendono potenziali falsi positivi e atti con più impianti o componenti. **Non equivalgono a 48 progetti o opportunità.** Non sono stati dedotti MW, autorizzazioni, date di lavori o contractor.

Prossimo blocco:

1. Classificare la pertinenza e il dispositivo effettivo degli atti, con evidenza della pagina: richiesta non equivale a concessione; decisione ambientale non equivale automaticamente ad autorizzazione alla costruzione.
2. Estrarre i campi per impianto/componente senza duplicare potenze di gruppo, separando MW/MWp/MWn, MWh e potenze di accesso; mantenere i conflitti espliciti.
3. Collegare l'inventario Catalunya solo con prove documentali o riferimenti amministrativi deterministici; non usare somiglianze di nome per modificare date o stato.
4. Eseguire test semantici, smoke, backfill del collector, controlli di provenienza/replay e certificazione integrata prima di abilitarlo come tredicesima fonte.

La dashboard, il parser comune, il registry e i dodici collector ordinari restano invariati in questa PR. I moduli e gli artifact DOGC sono ancora uno strato di verifica separato.
