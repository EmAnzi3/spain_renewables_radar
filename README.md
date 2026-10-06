# Spain Renewables Radar

Radar fotovoltaico, eolico, BESS e ibrido in Spagna, da **fonti ufficiali e gratuite**, senza aggregatori commerciali.

**Fonti → eventi amministrativi → progetto unico → lifecycle → enrichment → scoring separato → quality gate → portale navigabile.**

## Il portale è consultabile

La versione verificata contiene **257 schede e 263 eventi**, con **12 fonti aggiornate su 13** nella finestra **29 settembre–5 ottobre 2026**. Stato **PARTIAL**: GVA non raggiungibile non immobilizza le fonti funzionanti. I dati GVA precedenti restano datati e contrassegnati; non vengono presentati come aggiornati.

Quattro sezioni: **Progetti, Province, Fonti e copertura, Avvisi da integrare**. Sono disponibili ricerca, filtri per tecnologia/stato/provincia/CCAA/fonte/MW/priorità, schede con cronologia e testi originali, esportazione CSV e navigazione mobile. I sei impianti BOPV e il lead Coalsema restano fuori dai totali del radar fino all'integrazione.

**[Run operativo 37441856639](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37441856639)**: aggiornamento parziale e portale verificati. **[Run di pubblicazione 37447214551](https://github.com/EmAnzi3/spain_renewables_radar/actions/runs/37447214551)**: preparazione e controlli browser SUCCESS; deploy SKIPPED perché GitHub Pages non è configurato. Nessun URL pubblico viene dichiarato disponibile.

### Consultazione immediata

Nel run di pubblicazione, scaricare l'artifact **radar-web-ready**, estrarlo e aprire **index.html**. Il file contiene già dati e interfaccia; non richiede un server o servizi a pagamento. I collegamenti alle fonti originali richiedono naturalmente Internet. Non applicare lo ZIP come patch del codice.

### Pubblicazione online: impostazione amministrativa richiesta

Nella repository, **Settings → Pages → Build and deployment → Source: GitHub Actions**. Poi **Actions → publish-radar-web → Run workflow**. Il valore iniziale `source_run=37441856639` seleziona la versione verificata; per aggiornamenti futuri scegliere un run operativo main riuscito.

Il workflow verifica l'artifact originale e ripete i controlli browser, poi pubblica e verifica la pagina effettivamente servita. **Non riscarica le fonti** e non modifica le date di acquisizione. Non cerca token amministrativi e non aggira i permessi della repository.

## Aggiornamento operativo e certificazione

- **Operativo:** `app.operational` permette aggiornamenti PARTIAL dichiarati, con commit dei dati validi, provenienza e stato per ogni fonte. Gli errori strutturali non sono successi parziali e non devono sostituire il database valido.
- **Certificazione completa:** il workflow `backfill-30d-validation` continua a richiedere tutte le 13 fonti e tutti i controlli. L'indisponibilità GVA rimane un failure di quella prova.
- **Pubblicazione:** `publish-radar-web` riusa soltanto un artifact verificato; pubblicare non equivale a una nuova scansione.

L'ultimo dataset completo storico del run **37406054339** aveva **256 schede / 262 eventi** prima delle correzioni successive. Il portale attuale conserva **Almagro I a 7,2 MW BESS** e **Cistérniga a 2,1 MW BESS**, con geografia e promotori verificati; non attribuire queste correzioni retroattivamente all'artifact storico.

Stato effettivo, hash, limiti e run in **CURRENT_STATE.md** e **docs/validation/2026-10-06-operational-portal.json**.

## Perimetro delle fonti

Collector nel codice: **BOE, BOCYL, BOA, BOJA, DOCM, DOE, BORM, BOCM, DOG, DOGC, AND_PUBLIC, GVA_PUBLIC, MITECO_SABIA**. Bollettini autonomici **9/17**. INE, REE e RAIPEE sono enrichment, non ulteriori collector.

BOPV è classificato ma non ancora un collector ordinario. BOP Valencia/Alicante/Castellón, Delegazione del Governo e ICV sono percorsi alternativi pubblici in sviluppo, non una sostituzione completa GVA. I relativi avvisi restano nella sezione **Avvisi da integrare** e non sono automaticamente nuove schede o autorizzazioni.

SABIA mantiene i milestone ENTRY/CONSULT. I dati di rete REE non provano l'accesso di un singolo progetto. Gli inventari Catalunya/Galicia non trasformano date del dataset o scomparsa da un elenco in nuove pubblicazioni o ritiri.

## Avvio Windows

```bat
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
aggiorna_radar_web.bat
```

Il nuovo launcher esegue l'aggiornamento operativo e apre la pagina. Il precedente `aggiorna_radar_spagna.bat` resta disponibile. Aggiornare prima la copia locale di main: i commit remoti non modificano automaticamente il database sul PC.

Backfill rigoroso:

```bat
.\.venv\Scripts\python.exe -m app.run_pipeline --days 30 --strict-coverage
```

Inventari separati:

```bat
aggiorna_inventario_catalogna.bat
.\.venv\Scripts\python.exe -m app.galicia_archive
```

Non eliminare baseline e database per gli aggiornamenti ordinari. Un errore di rete non fa diventare l'ultimo report valido un'acquisizione nuova.

## Regole

Mai inventare nome, potenza, provincia, expediente, EPC o date. Promotore distinto da costruttore; richiesta distinta da concessione; scoring separato dal lifecycle. MW, MWh, kVA/MVA, potenza preesistente e nuova installazione restano distinti. I MW mancanti non sono zeri reali; i multi-provincia non duplicano la potenza nei totali. Stato autorizzato non significa cantiere avviato. Test verdi non garantiscono disponibilità futura o completezza assoluta delle fonti.
