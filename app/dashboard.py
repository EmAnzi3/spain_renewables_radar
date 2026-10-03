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
.table{background:#fff;border:1px solid var(--line);border-radius:16px;overflow:auto}.section{margin:26px 0 10px}.note{color:var(--muted);font-size:13px}table{border-collapse:collapse;width:100%;min-width:980px}th,td{padding:10px 12px;border-bottom:1px solid #edf0f4;text-align:left;font-size:13px}th{background:#f8fafc}.stage{font-weight:700}.PRECONSTRUCTION{color:#0b57d0}.AUTHORIZED{color:#137333}.PERMITTING{color:#ad6500}.BLOCKED{color:#b42318}.EARLY{color:#475467}
@media(max-width:800px){.cards{grid-template-columns:repeat(2,1fr)}.wrap{padding:16px}}
</style></head><body><div class="wrap"><div class="head"><div><h1>Spain Renewables Radar</h1><p class="sub">Fonti ufficiali gratuite · lifecycle amministrativo</p></div><div id="updated"></div></div>
<div class="cards"><div class="card"><div class="n" id="count">0</div><div class="lab">progetti</div></div><div class="card"><div class="n" id="mw">0 MW</div><div class="lab">MW identificati</div></div><div class="card"><div class="n" id="auth">0</div><div class="lab">maturi / pre-cantiere</div></div><div class="card"><div class="n" id="prov">0</div><div class="lab">province</div></div></div>
<h2 class="section">Vista provinciale</h2><p class="note">MW = solo potenza identificata; i progetti senza MW sono separati.</p><div class="table"><table><thead><tr><th>Provincia</th><th>Progetti</th><th>MW noti</th><th>Senza MW</th><th>FV</th><th>Eolico</th><th>BESS/ibrido</th><th>EARLY</th><th>PERMITTING</th><th>AUTHORIZED</th><th>PRECONSTRUCTION</th></tr></thead><tbody id="provinceRows"></tbody></table></div><h2 class="section">Opportunità</h2><div class="filters" id="filters"></div><div class="table"><table><thead><tr><th>Priorità</th><th>Score</th><th>Progetto</th><th>Tecnologia</th><th>MW</th><th>Promotore</th><th>EPC / BoP</th><th>Expediente</th><th>Provincia</th><th>CCAA</th><th>Stato</th><th>Ultimo evento</th><th>Fonte</th></tr></thead><tbody id="rows"></tbody></table></div></div>
<script>
let data=[],provinces=[],active='ALL';const fmt=n=>new Intl.NumberFormat('it-IT',{maximumFractionDigits:1}).format(n||0);
function render(){const f=active==='ALL'?data:data.filter(x=>x.technology===active);count.textContent=f.length;mw.textContent=fmt(f.reduce((s,x)=>s+(x.power_mw||0),0))+' MW';auth.textContent=f.filter(x=>['AUTHORIZED','PRECONSTRUCTION'].includes(x.commercial_stage)).length;prov.textContent=new Set(f.map(x=>x.province).filter(Boolean)).size;rows.innerHTML=f.map(x=>`<tr><td><b>${x.commercial_priority||'—'}</b></td><td>${x.commercial_score??'—'}</td><td>${x.project_name||'—'}</td><td>${x.technology||'—'}</td><td>${x.power_mw?fmt(x.power_mw):'—'}</td><td>${x.promoter||'—'}</td><td>${x.epc_status||'EPC_UNKNOWN'}${x.epc_name?' · '+x.epc_name:''}</td><td>${x.expediente||'—'}</td><td>${x.province||'—'}</td><td>${x.ccaa||'—'}</td><td class="stage ${x.commercial_stage}">${x.commercial_stage}</td><td>${x.latest_event_type}</td><td>${x.latest_source_url?`<a target="_blank" href="${x.latest_source_url}">${x.latest_source_code||'fonte'}</a>`:'—'}</td></tr>`).join('')}
function renderProvinces(){provinceRows.innerHTML=provinces.map(x=>`<tr><td><b>${x.province}</b></td><td>${x.projects}</td><td>${fmt(x.known_mw)}</td><td>${x.projects_without_mw}</td><td>${x.pv}</td><td>${x.wind}</td><td>${x.bess_hybrid}</td><td>${x.early}</td><td>${x.permitting}</td><td>${x.authorized}</td><td>${x.preconstruction}</td></tr>`).join('')}
function setup(){const types=['ALL','PV','WIND','BESS','HYBRID'];filters.innerHTML=types.map(t=>`<button data-t="${t}" class="${t==='ALL'?'on':''}">${t}</button>`).join('');document.querySelectorAll('button[data-t]').forEach(b=>b.onclick=()=>{active=b.dataset.t;document.querySelectorAll('button[data-t]').forEach(x=>x.classList.toggle('on',x===b));render()})}
fetch('data.json').then(r=>r.json()).then(j=>{data=j.records||[];provinces=j.provinces||[];updated.textContent='Dataset locale';setup();renderProvinces();render()}).catch(()=>setup());
</script></body></html>'''

def write_dashboard(path="docs/index.html"):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(HTML,encoding="utf-8");return p
