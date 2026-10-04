from __future__ import annotations
from pathlib import Path

HTML=r'''<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Spain Renewables Radar</title>
<style>
:root{--bg:#f4f7fb;--card:#fff;--ink:#13233a;--muted:#667085;--line:#d9e1ea}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font-family:Arial,Helvetica,sans-serif;color:var(--ink)}
.wrap{max-width:1280px;margin:auto;padding:28px}.head{display:flex;gap:18px;align-items:end;justify-content:space-between;flex-wrap:wrap}
h1{margin:0;font-size:32px}.sub{color:var(--muted);margin:8px 0 0}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:22px 0}.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}.n{font-size:28px;font-weight:700}.lab{color:var(--muted);font-size:13px}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.filters button{background:#fff;border:1px solid var(--line);border-radius:999px;padding:9px 13px;cursor:pointer}.filters button.on{border-color:#111827;font-weight:700}
.table{background:#fff;border:1px solid var(--line);border-radius:16px;overflow:auto}.section{margin:26px 0 10px}.note{color:var(--muted);font-size:13px;line-height:1.5}.filters input,.filters select{padding:9px 12px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink)}.small{display:block;font-size:12px;color:var(--muted);margin-top:5px;line-height:1.4}details{font-size:12px}td{vertical-align:top}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #2563eb;outline-offset:2px}table{border-collapse:collapse;width:100%;min-width:980px}th,td{padding:10px 12px;border-bottom:1px solid #edf0f4;text-align:left;font-size:13px}th{background:#f8fafc}.stage{font-weight:700}.PRECONSTRUCTION{color:#0b57d0}.AUTHORIZED{color:#137333}.PERMITTING{color:#ad6500}.BLOCKED{color:#b42318}.EARLY{color:#475467}
@media(max-width:800px){.cards{grid-template-columns:repeat(2,1fr)}.wrap{padding:16px}}
</style></head><body><div class="wrap"><div class="head"><div><h1>Spain Renewables Radar</h1><p class="sub">Fonti ufficiali gratuite · lifecycle amministrativo</p></div><div id="updated"></div></div>
<div class="cards"><div class="card"><div class="n" id="count">0</div><div class="lab">progetti</div></div><div class="card"><div class="n" id="mw">0 MW</div><div class="lab">MW identificati</div></div><div class="card"><div class="n" id="auth">0</div><div class="lab">maturi / pre-cantiere</div></div><div class="card"><div class="n" id="prov">0</div><div class="lab">province</div></div></div>
<div class="filters"><input id="search" type="search" aria-label="Cerca progetti, promotori o expediente" placeholder="Cerca progetto, promotore, expediente"><select id="sourceFilter" aria-label="Filtra per fonte"><option value="ALL">Tutte le fonti</option></select><div id="filters"></div></div><p class="note" id="dataNotice" role="status"></p><h2 class="section">Vista provinciale</h2><p class="note">MW = sola potenza identificata. I progetti multi-provincia sono conteggiati a parte, senza dividere o duplicare i loro MW.</p><p class="note" id="geographyNotice"></p><div class="table"><table><thead><tr><th>Provincia</th><th>Progetti</th><th>MW noti</th><th>Senza MW</th><th>FV</th><th>Eolico</th><th>BESS/ibrido</th><th>EARLY</th><th>PERMITTING</th><th>AUTHORIZED</th><th>PRECONSTRUCTION</th><th>BLOCKED</th></tr></thead><tbody id="provinceRows"></tbody></table></div><h2 class="section">Opportunità</h2><p class="note">Priorità = ordine commerciale, non probabilità di autorizzazione. La data SABIA indica un passaggio del procedimento, non la pubblicazione web. Nessun EPC viene ricavato dal nome del promotore.</p><div class="table"><table><thead><tr><th>Priorità</th><th>Score</th><th>Progetto</th><th>Tecnologia</th><th>MW</th><th>Promotore</th><th>EPC / BoP</th><th>Expediente</th><th>Provincia</th><th>CCAA</th><th>Stato</th><th>Ultimo evento / data</th><th>Fonte</th></tr></thead><tbody id="rows"></tbody></table></div></div>
<script>

'use strict';
let data=[],active='ALL';
const $=id=>document.getElementById(id);
const fmt=n=>new Intl.NumberFormat('it-IT',{maximumFractionDigits:3}).format(n);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const stages=['EARLY','PERMITTING','AUTHORIZED','PRECONSTRUCTION','BLOCKED'];
const techLabels={ALL:'Tutte le tecnologie',PV:'Fotovoltaico',WIND:'Eolico',BESS:'BESS',HYBRID:'Ibrido'};
const basisLabels={SOURCE_PUBLICATION:'Pubblicazione della fonte',ENTRY_DATE:'Ingresso nel procedimento',CONSULTATION_START:'Inizio delle consultazioni'};
function link(url,label){try{const u=new URL(url);if(!['http:','https:'].includes(u.protocol))return '—';return `<a target="_blank" rel="noopener noreferrer" href="${esc(u.href)}">${esc(label)}</a>`;}catch{return '—';}}
function validMW(x){return typeof x.power_mw==='number'&&Number.isFinite(x.power_mw)&&x.power_mw>0;}
function locations(x){return Array.isArray(x.provinces)&&x.provinces.length?x.provinces:(x.province?[x.province]:[]);}
function filtered(){const q=$('search').value.toLocaleLowerCase('it-IT').trim();return data.filter(x=>(active==='ALL'||x.technology===active)&&($('sourceFilter').value==='ALL'||x.latest_source_code===$('sourceFilter').value)&&(!q||[x.project_name,x.promoter,x.expediente,...locations(x)].join(' ').toLocaleLowerCase('it-IT').includes(q)));}
function provinceSummary(records){const map=new Map();for(const x of records){const loc=locations(x);if(loc.length!==1)continue;const p=loc[0];if(!map.has(p))map.set(p,{province:p,projects:0,known_mw:0,projects_without_mw:0,pv:0,wind:0,bess_hybrid:0,early:0,permitting:0,authorized:0,preconstruction:0,blocked:0});const r=map.get(p);r.projects++;if(validMW(x))r.known_mw+=x.power_mw;else r.projects_without_mw++;if(x.technology==='PV')r.pv++;if(x.technology==='WIND')r.wind++;if(['BESS','HYBRID'].includes(x.technology))r.bess_hybrid++;if(stages.includes(x.commercial_stage))r[x.commercial_stage.toLowerCase()]++;}return [...map.values()].sort((a,b)=>b.known_mw-a.known_mw||a.province.localeCompare(b.province));}
function regionalDetails(x){
 const records=x.regional_source_evidence||[];if(!records.length)return '';
 const labels={LEGAL_ACT_IMAGE_ONLY:'Atto scansionato: campi estratti dal titolo',MULTI_COMPONENT_POWER_NOT_SUMMED:'Potenze dei componenti distinte, non sommate',SOURCE_POWER_DISAGREEMENT:'Potenza da verificare: titolo e atto discordanti',SOURCE_PROVINCE_DISAGREEMENT:'Provincia discordante nelle fonti'};
 const powerLabels={installed:'Potenza installata',project_power:'Potenza del progetto',storage_module:'Modulo batterie',pv_peak:'Picco fotovoltaico',pv_inverters:'Inverter fotovoltaici',grid_access:'Capacità di accesso alla rete'};
 const bodies=records.map(r=>{const evidence=r.extraction?.evidence||{};const flags=(r.quality_flags||[]).map(f=>`<span class="small">${esc(labels[f.code]||f.code)}</span>`).join('');
 const unique=new Map();for(const p of evidence.power_assertions||[]){unique.set([p.basis,p.original_value,p.original_unit].join('|'),p);}
 const powers=[...unique.values()].map(p=>`<span class="small">${esc(powerLabels[p.basis]||p.basis)}: ${esc(p.original_value)} ${esc(p.original_unit)}</span>`).join('');
 return `<span class="small">${link(r.source_url,r.source_code+' · '+r.publication_date)}</span>${flags}${powers}`;}).join('');
 return `<details class="small"><summary>Dati e verifiche della fonte</summary>${bodies}</details>`;
}
function render(){
 const f=filtered(),known=f.filter(validMW),multi=f.filter(x=>locations(x).length>1),unknown=f.filter(x=>locations(x).length===0);
 $('count').textContent=f.length;$('mw').textContent=known.length?fmt(known.reduce((s,x)=>s+x.power_mw,0))+' MW':'MW non disponibili';
 $('auth').textContent=f.filter(x=>['AUTHORIZED','PRECONSTRUCTION'].includes(x.commercial_stage)).length;
 $('prov').textContent=new Set(f.flatMap(locations)).size;
 const grouped=new Map();for(const x of f){if(x.source_group_id&&x.group_unallocated_power_mw!=null)grouped.set(x.source_group_id,x.group_unallocated_power_mw);}
 $('dataNotice').textContent=`${known.length} progetti con MW identificati; ${f.length-known.length} senza MW. ${grouped.size?`${fmt([...grouped.values()].reduce((a,b)=>a+b,0))} MW dichiarati per gruppi di impianti: non sommati alle potenze individuali.`:''}`;
 $('geographyNotice').textContent=`${multi.length} progetti multi-provincia (${fmt(multi.filter(validMW).reduce((s,x)=>s+x.power_mw,0))} MW noti, non ripartiti). ${unknown.length} progetti con provincia da verificare.`;
 $('provinceRows').innerHTML=provinceSummary(f).map(x=>`<tr><td><b>${esc(x.province)}</b></td><td>${x.projects}</td><td>${x.projects>x.projects_without_mw?fmt(x.known_mw):'—'}</td><td>${x.projects_without_mw}</td><td>${x.pv}</td><td>${x.wind}</td><td>${x.bess_hybrid}</td><td>${x.early}</td><td>${x.permitting}</td><td>${x.authorized}</td><td>${x.preconstruction}</td><td>${x.blocked}</td></tr>`).join('');
 $('rows').innerHTML=f.map(x=>{
  const loc=locations(x),stage=stages.includes(x.commercial_stage)?x.commercial_stage:'EARLY';
  const group=x.source_group_id?`<span class="small">Componente della pratica ${esc(x.environmental_code||x.source_group_id)}${x.group_unallocated_power_mw!=null?' · '+fmt(x.group_unallocated_power_mw)+' MW del gruppo, non ripartiti':''}</span>`:'';
  const basis=x.date_basis||(x.latest_source_code==='MITECO_SABIA'?null:'SOURCE_PUBLICATION');
  const state=x.source_current_state?`<span class="small">Stato ambientale SABIA: ${esc(x.source_current_state)}</span>`:'';
  const score=Object.entries(x.score_components||{}).map(([k,v])=>`${esc(k)}: ${esc(v)}`).join('<br>');
  return `<tr><td><b>${esc(x.commercial_priority||'—')}</b></td><td><details><summary>${esc(x.commercial_score??'—')}</summary>${score}</details></td><td>${esc(x.project_name||'Nome non disponibile')}${group}</td><td>${esc(techLabels[x.technology]||x.technology||'—')}</td><td>${validMW(x)?fmt(x.power_mw):'—'}${regionalDetails(x)}</td><td>${esc(x.promoter||'—')}</td><td>${esc(x.epc_status||'EPC_UNKNOWN')}${x.epc_name?'<span class="small">'+esc(x.epc_name)+'</span>':''}</td><td>${esc(x.expediente||'—')}</td><td>${esc(loc.join('; ')||'Da verificare')}${loc.length>1?'<span class="small">Multi-provincia</span>':''}</td><td>${esc(x.ccaa||'—')}</td><td class="stage ${stage}">${esc(x.commercial_stage||'—')}${state}</td><td>${esc(x.latest_event_type||'—')}<span class="small">${esc(x.last_seen||'')} · ${esc(basisLabels[basis]||'Data amministrativa da verificare')}</span></td><td>${link(x.latest_source_url,x.latest_source_code||'fonte')}</td></tr>`;
 }).join('');
}
function setup(){
 $('filters').innerHTML=Object.entries(techLabels).map(([t,label])=>`<button type="button" data-t="${t}" class="${t==='ALL'?'on':''}" aria-pressed="${t==='ALL'}">${label}</button>`).join('');
 document.querySelectorAll('button[data-t]').forEach(b=>b.onclick=()=>{active=b.dataset.t;document.querySelectorAll('button[data-t]').forEach(x=>{x.classList.toggle('on',x===b);x.setAttribute('aria-pressed',String(x===b));});render();});
 const sources=[...new Set(data.map(x=>x.latest_source_code).filter(Boolean))].sort();
 $('sourceFilter').innerHTML='<option value="ALL">Tutte le fonti</option>'+sources.map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join('');
 $('search').oninput=render;$('sourceFilter').onchange=render;
}
fetch('data.json').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json();}).then(j=>{if(!Array.isArray(j.records))throw Error('Formato dati non valido');data=j.records;$('updated').textContent='Dataset locale · '+data.length+' progetti';setup();render();}).catch(()=>{$('updated').textContent='Dati non caricati';$('dataNotice').textContent='Impossibile caricare data.json. Aprire la dashboard dal server locale del radar.';setup();});
</script></body></html>'''

def write_dashboard(path="docs/index.html"):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(HTML,encoding="utf-8");return p
