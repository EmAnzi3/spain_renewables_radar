# CURRENT STATE — Spain Renewables Radar

Checkpoint **6 ottobre 2026, Europe/Rome**. Lavoro su `main`. **Il radar operativo prosegue anche con una fonte indisponibile; il portale navigabile contiene 257 schede e 263 eventi. GitHub Pages richiede ancora attivazione amministrativa: il sito pubblico non è dichiarato online.**

Questo checkpoint supera le descrizioni precedenti che fermavano tutto il lavoro al preflight GVA. Il preflight rimane nel workflow di certificazione completa, non blocca il nuovo aggiornamento operativo parziale. Lo storico dettagliato resta nella [revisione f7b6878](https://github.com/EmAnzi3/spain_renewables_radar/blob/f7b68784789e3f87ce525e7efae5c6ef3c311285/CURRENT_STATE.md) e nei checkpoint di fonte.

## Aggiornamento operativo verificato

Run **37441856639**, codice **f7b68784789e3f87ce525e7efae5c6ef3c311285**, build SUCCESS; deploy SKIPPED perché Pages non configurato. Finestra tentata **29 settembre–5 ottobre 2026**. Completamento originale **2026-10-06T09:27:13.558058+00:00** (11:27 Europe/Rome).

- **257 schede progetto / 263 eventi** nel database persistente; non 257 nuovi cantieri né 257 nuove opportunità del periodo.
- **12 fonti COMPLETE su 13**, sette giorni per ogni fonte completata; **GVA_PUBLIC UNAVAILABLE**.
- Stato **PARTIAL**, `database_promoted=true`, `full_certification=false`.
- Gli atti precedenti GVA restano nel database con le proprie date: **16 schede** hanno almeno una fonte non aggiornata in questa esecuzione.
- Quality gate operativo: **0 ERROR / 9 WARN / 184 INFO**. Restano **69 schede senza MW, 39 senza expediente, 2 senza nome**. I nove casi senza provincia singola sono multi-provincia; **zero province realmente irrisolte**.
- Geografia: 648,16 MW multi-provincia non ripartiti né duplicati; 30 MW del gruppo SABIA 20260224 restano non allocati.
- Distribuzione degli stati del dataset: **156 EARLY, 47 PERMITTING, 30 AUTHORIZED, 9 PRECONSTRUCTION, 15 BLOCKED**. Stato amministrativo e avvio effettivo dei lavori non sono equivalenti.

La pagina e il database scaricati sono stati confrontati per tutte le 257 chiavi e per nome, tecnologia, MW, promotore, provincia e stato: coincidenti. Il database supera `PRAGMA integrity_check`.

Artifact originali verificati per byte/digest:

| Artifact | ID | Byte | SHA256 |
|---|---|---:|---|
| radar-web-navigable | 11402510121 | 39205152 | bec88d91aebf8ba6c12c63e0d03a543692d64fefb2f44749ba57e681ffabaf2a |
| radar-operational-state | 11401189832 | 5953600 | bef7224476595a797b834884b33984ef1260e5c2e240697511d82f18f18f0c94 |

## Portale consultabile e pubblicazione separata

Il portale `web/portal.html` generato da `app.web_portal` è autonomo: dati inclusi nella pagina, nessuna API o libreria esterna richiesta per filtrare e navigare. Contiene **Progetti, Province, Fonti e copertura, Avvisi da integrare**, schede con eventi/testi originali, filtri, priorità commerciali e CSV della selezione.

**Nuovo workflow `publish-radar-web`**, codice **f2a21b72c469d2d0f33f1e2af00f6754c795b80f**. Il run **37447214551** ha completato il job `prepare` con SUCCESS; `deploy` è SKIPPED per Pages non configurato. La suite esistente e i sette nuovi test di integrità sono passati. Il controllo Chromium desktop/mobile è passato sui dati effettivi: ricerca/scheda, Almagro, tecnologia, province, copertura, lead separati, zero errori JavaScript, nessun overflow a 390 px.

Questo workflow **non rilancia i collector**: recupera un artifact navigabile di un run operativo main riuscito, verifica digest, contenuto HTML/JSON, numero e identità dei progetti, esito browser e stato delle fonti. Conserva integralmente date e contenuti originali. Non trasforma PARTIAL in certificazione completa. In caso di deploy verifica anche l'hash della pagina realmente servita all'URL pubblico.

**Artifact pronto `radar-web-ready`, ID 11404285981**: **2524740 byte**, SHA256 **dfec066e7d01971b63323b5eab48ca3187292a9abef17333db1eac914bd652e7**, scaricato e verificato. Estrazione e apertura di `index.html`; non serve un server per le funzioni della pagina. Il suo HTML coincide byte per byte con il portale operativo originale, SHA256 **633a3df78a7bf9c51150a3943a46dc9586255bb12fb57e92cc56ae8273c1f0fe**.

### Passaggio amministrativo ancora necessario

La lettura autenticata della configurazione Pages restituisce **404**, stato `PAGES_CONFIGURATION_REQUIRED`; `public_site_verified=false`. I tool GitHub disponibili non espongono una scrittura amministrativa Pages. L'azione ufficiale di abilitazione richiede un token amministrativo diverso dal normale GITHUB_TOKEN: non sono stati richiesti o ricercati segreti.

Nella repository: **Settings → Pages → Build and deployment → Source: GitHub Actions**. Poi eseguire **Actions → publish-radar-web → Run workflow**, lasciando `source_run=37441856639` per questa versione verificata. Non occorre ripetere l'acquisizione di tutte le fonti. Non indicare un URL come live finché il job deploy e la verifica HTTP non sono conclusi.

## Correzioni preservate nel portale effettivo

- **BESS Almagro I**: BESS **7,2 MW**, Almagro / Ciudad Real, expediente 13270209226, PUBLIC_INFO/EARLY. Non sono i 7,4 MW del FV preesistente. Correzione documentata e validata DOCM nel run 37420987930.
- **BESS Cistérniga**: BESS **2,1 MW**, Valladolid, promotore **Soluciones de Ingeniería Industrial II, S.L.**, PUBLIC_INFO/EARLY. Correzione pubblicata in f7b6878, con originale revisionato e migrazione protetta.
- Le riparazioni dei record preesistenti richiedono hash e vecchi valori attesi, backup SQLite, transazione e idempotenza. Non cambiano identità, URL, testo, date o lifecycle degli eventi.

## Fonti alternative e BOPV

Il portale rende già consultabili gli avvisi della **Delegazione del Governo della Comunitat Valenciana**, con testi e collegamenti documentali, e l'esito dei probe **BOP Valencia, Alicante, Castellón e ICV FV**. Sono fonti pubbliche alternative verificate come accessi, **non cinque nuovi collector certificati né una sostituzione completa GVA**. I dati geografici ICV rimangono contesto/inventario, non eventi datati.

**BOPV**: classificazione verificata, sei impianti energetici più un lead industriale Coalsema, conservati nella sezione separata. Cinque PUBLIC_INFO/EARLY e una DIA/PERMITTING. **BOPV resta `implemented=false` e non entra nelle 257 schede**. Indice 37420987792, classificazione 37428902802 e replay su main 37430217754; dettagli in `docs/sources/bopv.md`.

Restano da completare i collector alternativi regionali e il collector BOPV live, con persistenza, smoke e backfill. Non sommare avvisi da integrare e schede del radar per gonfiare i totali.

## Certificazione completa distinta dall'operatività

L'ultimo backfill rigoroso a 13 fonti concluso rimane **37406054339**, codice 88201b5, finestra 6 settembre–5 ottobre 2026: **256 schede / 262 eventi**. Quell'artifact storico precede le correzioni successive e non viene riscritto. I tentativi rigorosi successivi falliti su GVA restano falliti, incluso **37441856595** su f7b6878. Il successo operativo PARTIAL non li sostituisce.

13 collector nel codice: BOE, BOCYL, BOA, BOJA, DOCM, DOE, BORM, BOCM, DOG, DOGC, AND_PUBLIC, GVA_PUBLIC, MITECO_SABIA. Bollettini CCAA **9/17**. INE, REE e RAIPEE sono enrichment. Mancanti DOGV, BON, BOPV, BOPA, BOCANT, BOC-CAN, BOIB, BOR. EPC/BoP esterno resta successivo alla discovery.

## Uso e vincoli

`aggiorna_radar_web.bat` avvia l'aggiornamento operativo parziale e apre il portale; `aggiorna_radar_spagna.bat` rimane il launcher precedente. `publish-radar-web` pubblica invece un risultato già acquisito, senza rete verso le fonti.

Solo fonti ufficiali/gratuite, nessun aggregatore commerciale. Preservare external_id, raw_text, URL, date e ruoli. Promotore distinto da EPC, richiesta distinta da concessione, scoring distinto dal lifecycle. Campi sconosciuti e multi-provincia espliciti; nessun valore inventato. Non confondere dataset persistente, nuova finestra acquisita, classificazione di lead, test, certificazione completa e pubblicazione effettiva.
