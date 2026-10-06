# BOPV — indice riconciliato e classificazione verificata

Stato **6 ottobre 2026**: classificazione sul perimetro **6 settembre–5 ottobre 2026** completata e integrata in main tramite PR #2. **Collector non abilitato, nessun evento creato nel database ordinario.**

## Provenienza e perimetro

Indice **37420987792 — SUCCESS**: ricerca ufficiale su 31 pagine, 306 disposizioni confrontate con i sommari delle 21 edizioni dei calendari ufficiali, 30 giorni inclusi nove senza edizione. Nessuna omissione o differenza sostanziale di titolo/identità. Cinque testi HTML completi e relative date verificati. Artifact11393276447,753694byte,SHA25635f211924f8309c2b14a8e7d6990cbd70ee86e77d076db97671ffb7d9bd8a885. Metodo e probe precedenti restano nei checkpoint 2026-10-06-bopv-preflight.json e 2026-10-06-almagro-bopv.json.

Il classificatore ricostruisce prima l'intero indice dai file originali, non si fida del solo elenco generato. Date degli atti e di pubblicazione restano distinte. Non vengono letti domini diversi da quelli ufficiali né aggiunti dati da aggregatori.

## Moduli e validazione

`app/bopv_semantics.py` è una trasformazione pura senza rete o database. `scripts/validate_bopv_semantics.py` ricostruisce l'indice originale, verifica gli hash, classifica tutti i candidati, confronta cinque casi revisionati e ripete la trasformazione senza mutare input o creare identità casuali. Fixture `tests/fixtures/bopv_semantic_review.json`; **34 test** di errori e regressione in `tests/test_bopv_semantics.py`.

Classificazione **37428902802 — SUCCESS**, codice81bbcd0ccf74b953e1eb4ee28c7da39ad6ab2484. Ripetuta su main **37430217754 — SUCCESS**, codedc4630627ac3043e70bb644a27ce0942ad0580f4. Artifact11396013105,177904byte,SHA2568dc9a0133c708c6cf3bfca39f065790683f05069b54e3556197d798a09999e52, scaricato e verificato anche ricalcolando localmente tutti i campi dagli HTML originali. È un replay degli originali acquisiti, non una nuova data di pubblicazione o una nuova scansione live.

## Risultati per impianto

| Atto / pubblicazione | Impianto | MW espliciti | Localizzazione | Evento |
|---|---|---:|---|---|
| 2026/04004 — 24 settembre | Hernani I | 4,99 | Villabona, Gipuzkoa | PUBLIC_INFO / EARLY |
| 2026/04004 — 24 settembre | Hernani II | 4,99 | Villabona, Gipuzkoa | PUBLIC_INFO / EARLY |
| 2026/03989 — 23 settembre | Regina Solar | 10,12 | Vitoria-Gasteiz e Arratzua-Ubarrundia, Álava | PUBLIC_INFO / EARLY |
| 2026/03989 — 23 settembre | Nova Solar | 1 | Vitoria-Gasteiz, Álava | PUBLIC_INFO / EARLY |
| 2026/03987 — 23 settembre | Pe Pando | 30 | Ayala e Okondo, Álava | PUBLIC_INFO / EARLY |
| 2026/03902 — 16 settembre | Mendi | 31,2 | Amurrio e Ayala, Álava | DIA / PERMITTING |

Quattro atti producono **sei impianti energetici**, non sei cantieri autorizzati. Mendi contiene una dichiarazione ambientale, non un permesso di costruzione. L'atto 2026/03988, pubblicato il23settembre, riguarda **Coalsema**, un ibrido industriale per autoconsumo: conservato come **SELF_CONSUMPTION_LEAD** distinto, con MW di progetto non assegnati e richiesta PUBLIC_INFO/EARLY.

Hernani I e II hanno dossier condiviso20-GE-Y-2025-00004, ma promotori distinti Premier ESPF Ipaz Haizea,S.L. e Premier ESPF Ipaz Haizea2,S.L.; l'applicant comune Premier ESPF Renovables,S.L. non sostituisce gli owner. La sede degli aerogeneratori è Villabona; i comuni attraversati dalla linea non sono assegnati arbitrariamente alla generazione.

Regina e Nova conservano rispettivamente01–GE–Y–2025–00021 e01–GE–Y–2025–00031, senza prendere i dossier degli altri impianti che condividono l'evacuazione. Pando e Mendi non hanno un riferimento individuale univoco nel testo: expediente vuoto, identità provvisoria. GE–Y è una categoria di procedimento, non un codice completo inventato.

Coalsema: potenza apparente FV in kVAn, potenza PCS in kW, kWh per contenitore e cogenerazione preesistente sono quantità distinte. Non vengono sommati né convertiti impropriamente in un unico MW. L'impianto industriale rimane visibile come lead, non eliminato o presentato come nuovo parco utility-scale.

## Evidenze e limiti

Ogni campo conserva indice del paragrafo, intervallo, testo originale e SHA256 del paragrafo. Tutte le quantità sono conservate con unità/basi e `automatically_summable=false`. EPC e date lavori restano vuoti. Conflitti espliciti lasciano il campo scalare sconosciuto; dispositivo non riconosciuto resta REVIEW_REQUIRED e fa fallire la validazione dei candidati.

La lettura comprende titoli, paragrafi e intestazioni di dispositivo anche quando il DOM usa h6.BOPVClave. Le tabelle indicate dalla fonte come presenti solo nel PDF sono segnalate: non sono state interpretate o trasformate in coordinate inventate.

Output artifact: index.html, assets.csv, classified_documents.json, originals/ e validation_metrics.json. Prima dell'abilitazione di BOPV sono necessari collector live, strategia di persistenza delle identità provvisorie, smoke, backfill e certificazione integrata. Non sommare questi sei impianti ai conteggi storici del radar finché non vengono realmente acquisiti e deduplicati nel database.
