# BOPV — fonte pubblica verificata, collector non ancora implementato

Checkpoint **6 ottobre 2026**. Il probe ufficiale è stato eseguito dal runner GitHub. Il registry rimane `implemented=false`: non sono stati creati eventi BOPV né modificati i tredici collector operativi.

## Prova acquisita e verificata

- Run **37402681950 — SUCCESS**, codice **dba855e6165653fe63f33e9e2a0ff0b3cea54792**.
- Workflow `.github/workflows/bopv-date-index-probe.yml`, script `.github/scripts/probe_bopv_dates.py`.
- Finestra richiesta e conservata in ogni pagina: **6 settembre–5 ottobre 2026**.
- **31 pagine della ricerca, 306 disposizioni univoche**, conteggio riconciliato con il totale dichiarato dalla fonte.
- **Cinque titoli candidati**, tutti e cinque acquisiti come HTML integrali da URL ufficiali forniti dalla ricerca.
- **39 pagine HTML complessive**: home, calendario, form, ricerca paginata e cinque dettagli.
- Artifact **11386156031**, `bopv-date-index-probe-output`, **616.271 byte**, SHA256 **417ffc8ff68ad059fe0bd4d98c76e027f79aeb61501c9ea2de59214ca1dfd307**.
- Artifact scaricato e digest/dimensione confrontati con i metadati GitHub. Ricostruite localmente tutte le 31 pagine dagli HTML originali: i 306 record coincidono con `window_index.json`, senza identità ripetute.

Questa è una verifica della **paginazione della ricerca nella finestra**, non una certificazione del collector, della semantica di tutti gli atti o dell'intera copertura BOPV. Non è stato ancora eseguito un confronto indipendente completo con i sommari di tutti i giorni. Nel report del probe `complete_coverage_certified=false` e `individual_publication_dates_verified=false` rimangono correttamente espliciti.

## Percorso pubblico osservato

Origine: `https://www.euskadi.eus/bopv2/datos/Ultimo.shtml`.

La home collega la ricerca avanzata pubblica e incorpora un calendario attraverso `/bopv2/datos/CalUltimo.shtml`. Quest'ultimo contiene le liste JavaScript `diasHabilitados` ed `enlaces`: non ha normali link HTML navigabili. Nel campione di ottobre sono elencati 1, 2 e 5 ottobre con i relativi sommari. Occorre implementare e verificare la navigazione mensile ufficiale prima di affermare una copertura giornaliera indipendente.

Il form di ricerca avanzata osservato proviene da `/web01-bopv/es/p43aBOPVWebWar/buscarAvanzada.do?idioma=es&tipoBusqueda=2`. L'azione POST è quella restituita dal form; l'eventuale identificativo di sessione anonima non viene inventato o riusato da acquisizioni precedenti.

Parametri verificati:

- `buscarPorFechaBoletin=true`, `tipoBusquedaFecha=5`;
- `desdeFechaBoletin=06/09/2026`, `hastaFechaBoletin=05/10/2026`;
- nessun testo, filtro di sezione/rango/organismo o stato usato per ridurre la discovery;
- paginazione pubblica tramite form, `paginaActual` e `submit=Paginar`, come nel JavaScript del sito;
- `numeroRegistrosPagina=10`, `numeroRegistrosEncontrados=306`, 31 pagine dichiarate.

Ogni pagina deve mantenere finestra, numero pagina, dimensione e totale. Identità riportata e URL della disposizione devono concordare. Risposte troncate, sovrapposte, conteggi diversi o limiti del servizio non vengono nascosti deduplicando. Il codice sorgente della pagina avverte che ricerche molto grandi vengono limitate: il probe rifiuta risultati pari o superiori a 1.000; un futuro collector dovrà partizionare la ricerca senza omissioni.

## Documenti candidati conservati — non nuovi eventi certificati

| Identità BOPV | Oggetto nella fonte | Data leggibile nell'intestazione del dettaglio |
|---|---|---|
| 2026/04004 | Clúster Eólico Hernani I-II e infrastrutture comuni | 24 settembre 2026 |
| 2026/03989 | Regina Solar e Nova Solar | 23 settembre 2026 |
| 2026/03988 | Ibridazione Coalsema: cogenerazione esistente, FV e batterie | 23 settembre 2026 |
| 2026/03987 | Pe Pando | 23 settembre 2026 |
| 2026/03902 | Dichiarazione ambientale del parco eolico Mendi | 16 settembre 2026 |

Le date sopra sono state lette nei cinque dettagli acquisiti, non dedotte dalla data dell'atto. Il probe conserva ancora `publication_date=null` nei record dell'indice: il parser datato dei dettagli non è stato implementato/certificato. I cinque documenti possono contenere più impianti e componenti; **non equivalgono a cinque progetti unici**. In particolare, non sommare Regina/Nova, non confondere Hernani I-II con un solo impianto e non aggiungere la potenza della cogenerazione esistente alla nuova capacità rinnovabile Coalsema.

I primi quattro avvisi riguardano richieste/informazione pubblica e non vanno trasformati in concessioni. Per Mendi va letto il dispositivo ambientale completo prima della proiezione. Nessun nome, MW, EPC o data lavori è stato inserito nel database da questo probe.

## Prossimo blocco verificabile

Implementare il calendario/sommario datato e il parser dei dettagli, mantenere un rendiconto di ogni avviso candidato, distinguere impianti/componenti e richieste/concessioni. Aggiungere test su queste fonti originali, smoke live e backfill di trenta giorni, poi gate integrato di identità/provenienza/replay. Solo successivamente abilitare BOPV.

## Probe precedenti e limiti mantenuti

Il preflight **37399131568** ha rilevato BOPV raggiungibile ma **BON Navarra in timeout anche dopo due tentativi limitati**. Il suo SUCCESS non certifica BON. Il probe iniziale **37401685235** è fallito per un errore di sintassi del nostro script, prima di contattare la fonte. È stato corretto separando lo script Python e aggiungendo una compilazione preventiva; il successivo probe **37402192864** ha acquisito il form e la prima pagina, poi quello corrente tutte le pagine. I precedenti failure rimangono nello storico e non vengono riscritti come successi.
