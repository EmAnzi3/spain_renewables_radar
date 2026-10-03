# CURRENT STATE — Spain Renewables Radar

## Stato certificato

Il radar è operativo su **8 bollettini ufficiali** più **3 enrichment nazionali gratuiti**.

### Collector attivi

- BOE — nazionale
- BOCYL — Castilla y León
- BOA — Aragón
- BOJA — Andalucía
- DOCM — Castilla-La Mancha
- DOE — Extremadura
- BORM — Región de Murcia, tramite dataset ufficiale Open Data degli indici
- BOCM — Comunidad de Madrid, tramite fonte ufficiale per data/XML

### Enrichment attivi

- INE — catalogo ufficiale dei comuni, usato per enrichment deterministico comune → provincia/CCAA;
- REE — capacità/accesso per nodo, usato esclusivamente come contesto di rete;
- MITECO RAIPEE — registro produzione, con matching progetto ↔ impianto volutamente conservativo.

Nessun aggregatore commerciale è usato.

## Ultima certificazione completa

Codice certificato:

- head: **dcece22a899cdc607a539fdc973f2d256e21c9da**
- tests: **37134192242 — SUCCESS**
- smoke live: **37134192262 — SUCCESS**
- backfill 30 giorni rigoroso: **37134192228 — SUCCESS**
- source/day errors: **0**

### Dataset 30 giorni certificato

- **106 progetti**
- **128 eventi amministrativi**
- BOE 41
- BOCYL 15
- BOA 24
- BOJA 7
- DOCM 17
- DOE 8
- BORM 11
- BOCM 5
- REE: **931 nodi**, snapshot 2026-10-01
- MITECO: **71.727 impianti**, snapshot 2026-10-03
- matching MITECO esatti conservativi: **8**
- province aggregate nella vista provinciale: **29**

### Campi mancanti

- nome: **1**
- MW: **25**
- provincia singola: **1**
- expediente: **14**

Il solo progetto senza provincia singola è un caso **multi-provincia** identificato esplicitamente dall'enrichment geografico; non viene forzata una provincia arbitraria.

## Enrichment geografico

Blocco chiuso e certificato.

Sul backfill 30 giorni:

- progetti inizialmente senza provincia da arricchire: **3** dopo la rimozione del falso positivo BOE;
- risolti deterministicamente con catalogo INE: **2**;
- multi-provincia: **1**;
- irrisolti: **0**.

Regole consolidate:

- il comune viene cercato solo in contesti di localizzazione espliciti del testo;
- la relazione comune → provincia/CCAA deriva dal catalogo ufficiale INE;
- una provincia già presente e supportata dalla fonte non viene sovrascritta;
- i casi multi-provincia restano tali e non vengono schiacciati su una singola provincia;
- l'audit è salvato nella tabella project_geo_enrichment.

## Scoring commerciale

Blocco v1 chiuso e certificato.

Lo score commerciale è **separato dal lifecycle amministrativo** e non modifica i dati sorgente.

Tiene conto di:

- MW noti;
- lifecycle;
- milestone avanzate EXPROPRIATION e CONSTRUCTION_AUTH;
- recency dell'ultimo evento;
- tecnologia;
- disponibilità di contesto REE;
- stato EPC, oggi inizializzato a EPC_UNKNOWN;
- eventuale finestra lavori, oggi non valorizzata finché non esiste una fonte affidabile.

Output disponibili nel dashboard JSON:

- commercial_score
- commercial_priority
- score_components
- epc_status
- age_days

## Vista provinciale

Blocco v1 chiuso e certificato.

Generati:

- reports/province_view_latest.csv
- reports/province_view_latest.html
- sezione provinciale nel dashboard docs/index.html

Per provincia sono mostrati almeno:

- numero progetti;
- MW **conosciuti**;
- numero progetti senza MW;
- FV;
- eolico;
- BESS/ibrido;
- EARLY;
- PERMITTING;
- AUTHORIZED;
- PRECONSTRUCTION;
- BLOCKED.

I MW mancanti non vengono mai sommati come zero reale.

## Quality gate

Ultimo conteggio certificato:

- **ERROR: 0**
- **WARN: 1**
- **INFO: 40**

Il solo WARN sul nome è una pubblicazione BOCYL che raggruppa due parchi fotovoltaici senza fornire denominazioni individuali. Il radar conserva correttamente il nome vuoto.

Correzioni consolidate:

- falsi positivi Catasto/policy generiche BOE esclusi;
- falso positivo BOE “La Sabatería” eliminato: bateria richiede ora confini di parola;
- gigafactory batterie per veicoli BOA esclusa;
- storage non energetico DOCM escluso;
- centri rifiuti/riciclo pannelli DOE esclusi;
- nomi BESS/ibridi prioritari rispetto agli impianti preesistenti;
- virgolette tipografiche spagnole gestite;
- potenze in kW convertite in MW;
- fonti regionali vincolate alla propria CCAA;
- BORM acquisito da JSON ufficiale Open Data;
- BOCM acquisito dalla fonte ufficiale per data/XML e dotato di retry su errori 429/5xx;
- Expte. gestito come variante di expediente;
- retry BOA attivo per errori transitori.

## Problemi aperti

- 25 progetti non riportano MW nella fonte disponibile;
- 14 progetti non riportano expediente;
- 1 progetto è multi-provincia e resta correttamente senza provincia singola;
- matching MITECO resta volutamente conservativo;
- EPC/BoP non è ancora implementato;
- finestra lavori non è ancora un enrichment strutturato;
- DOGV risponde 403 dal runner GitHub e non va dichiarato implementato finché non si trova un endpoint ufficiale stabile.

## Prossimi passi

1. **enrichment EPC/BoP** da fonti pubbliche gratuite, mantenendo separati developer/promotore ed EPC;
2. aggiungere eventuale **work-window enrichment** solo quando supportato da fonti affidabili;
3. valutare il prossimo collector regionale con probe ufficiale, test, smoke live e backfill 30 giorni;
4. candidati prioritari: DOGC, BOPV, BON, DOG, BOPA, BOCANT, BOC Canarias, BOIB, BOR;
5. DOGV resta sospeso finché il 403 dal runner non viene risolto;
6. continuare a ridurre INFO e campi mancanti senza ricostruzioni fragili.

## Vincoli

- fonti ufficiali/gratuite come primary source;
- nessun Sondeva o aggregatore commerciale;
- meglio campo vuoto che dato inventato;
- owner/promotore ed EPC sono entità diverse;
- lifecycle amministrativo e scoring commerciale restano separati;
- REE è contesto rete, non conferma automatica del singolo progetto;
- un progetto resta una sola entità e accumula eventi successivi.
