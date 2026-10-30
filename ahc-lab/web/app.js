'use strict';
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeValue = v => Number.isFinite(v) && (!Number.isInteger(v) || Number.isSafeInteger(v));
const num = (v, digits=2) => v == null || !Number.isFinite(v) ? '—' : !safeValue(v) ? '精度範囲外' : v.toLocaleString('ja-JP',{maximumFractionDigits:digits});
const signed = (v, digits=2) => v == null ? '—' : (v>0?'+':'') + num(v,digits);
const tone = v => v == null || v === 0 ? 'dim' : v > 0 ? 'good' : 'bad';
const mean = xs => xs.length ? xs.reduce((a,b)=>a+b,0)/xs.length : null;
let state = null, chosen = '', base = '', selectionMade = false, pendingId = '', freezing = false;
async function api(path, data) {
  const r = await fetch(path, data ? {method:'POST',headers:{'Content-Type':'application/json','X-Lab-Token':state.token},body:JSON.stringify(data)} : {});
  const body = await r.json();
  if (!r.ok || body.error) throw Error(body.error || '通信できません');
  return body;
}
function error(e) { $('error').hidden = !e; $('error').textContent = e ? e.message : ''; }
function title(r) { return `${r.created_at.slice(5,19).replace('T',' ')} · ${r.label || r.id} · ${r.summary?.cases ?? 0}件`; }
function comparison(r,b) {
  if (!b || r.state!=='complete' || b.state!=='complete' || !r.evaluator_signature || r.evaluator_signature!==b.evaluator_signature) return {compatible:false, reason:'採点条件が同じ完了版を選んでください', pairs:new Map()};
  const old = new Map(b.rows.map(x=>[x.id,x])), pairs = new Map();
  for (const row of r.rows) {
    const prior = old.get(row.id);
    if (!prior || row.input_sha256!==prior.input_sha256) continue;
    let delta=null, percent=null;
    if(row.status==='ok' && prior.status==='ok') {
      delta=(row.score-prior.score)*(r.direction==='max'?1:-1);
      percent=prior.score!==0 ? 100*delta/Math.abs(prior.score) : null;
    }
    pairs.set(row.id,{delta,percent});
  }
  return {compatible:pairs.size>0, reason:pairs.size?'':'同じ入力がありません', pairs};
}
function logLink(r,row,name,label) {
  const params = new URLSearchParams({run:r.id,case:row?.folder || '',name});
  return `<a target="_blank" rel="noopener" href="/api/log?${params}">${label}</a>`;
}
function render() {
  const runs=state.runs;
  $('contest').textContent=state.name || '';
  $('conditions').textContent=state.ready===false?'問題公開後に設定':`${state.direction==='max'?'大きいほど良い':'小さいほど良い'} / ${state.workers}件ずつ実行`;
  $('source').textContent=`解答：${state.source}`;
  const active=state.active, busy=active && ['準備中','ビルド中','実行中'].includes(active.state);
  $('freeze').disabled=freezing;
  $('submission-dir').textContent=`保存先：${state.submission_dir || ''}`;
  $('submissions').innerHTML=(state.submissions || []).map(s=>{
    const tests=(s.matching_runs || []).slice(0,3).map(r=>`${r.summary?.cases || 0}件：成功${r.summary?.valid || 0} / 失敗${r.summary?.failed || 0}`).join('、') || '記録なし';
    const query=new URLSearchParams({file:s.filename});
    const links=s.intact ? `<a target="_blank" rel="noopener" href="/api/submission?${query}">表示</a> · <a href="/api/submission?${query}&download=1">ダウンロード</a>` : '<span class="bad">保存後に変更あり</span>';
    const actions=[10,100].map(n=>`<button data-submission="${esc(s.filename)}" data-count="${n}" ${busy || state.ready===false || !s.intact || state.available<n?'disabled':''}>${n}件実行</button>`).join(' ');
    return `<tr><td title="SHA-256: ${esc(s.sha256)}">${esc(s.filename)}</td><td>${esc(s.label || '—')}</td><td>${esc(s.created_at.slice(0,19).replace('T',' '))}</td><td>${esc(tests)}</td><td>${links}<div class="saved-actions">${actions}</div></td></tr>`;
  }).join('') || '<tr><td colspan="5" class="dim">まだ保存していません。</td></tr>';
  $('run10').disabled=!!busy || state.available<10 || state.ready===false;
  $('run100').disabled=!!busy || state.available<100 || state.ready===false;
  $('stop').disabled=!busy;
  $('status').textContent=state.ready===false ? state.setup_message || '問題公開後にテスト設定を行ってください' : busy ? `${active.state} ${active.done} / ${active.total}件` : `${active?.state || '準備完了'} · 入力${state.available}件（100件未満の場合は100ケース実行不可）`;
  // Preparing inputs/building can precede the first persisted result. Keep the new selection.
  if(!runs.some(r=>r.id===chosen) && chosen!==pendingId && chosen!==state.active?.id) chosen=runs[0]?.id || '';
  if(runs.some(r=>r.id===pendingId)) pendingId='';
  if(!selectionMade && chosen) {
    const cur=runs.find(r=>r.id===chosen);
    if(cur) base=runs.find(r=>r.id!==chosen && r.state==='complete' && r.evaluator_signature===cur.evaluator_signature)?.id || '';
  }
  $('current').innerHTML=runs.map(r=>`<option value="${esc(r.id)}">${esc(title(r))}</option>`).join('');
  $('current').value=chosen;
  $('baseline').innerHTML='<option value="">比較しない</option>'+runs.filter(r=>r.id!==chosen).map(r=>`<option value="${esc(r.id)}">${esc(title(r))}</option>`).join('');
  $('baseline').value=base;
  const r=runs.find(x=>x.id===chosen), b=runs.find(x=>x.id===base);
  $('empty').hidden=!!r; $('results').hidden=!r;
  if(!r) return;
  const s=r.summary || {}, comp=comparison(r,b), pairs=[...comp.pairs.values()], valid=pairs.filter(p=>p.delta!=null);
  const allValid = r.state==='complete' && s.cases>0 && s.failed===0;
  const delta=valid.length?valid.reduce((a,p)=>a+p.delta,0):null;
  $('summary').innerHTML=[
    ['生得点合計',allValid?num(s.score_sum):'—',allValid?'公式の相対スコアではありません':`成功分の合計：${num(s.score_sum)}（総合値は未確定）`],
    ['成功 / 失敗',`${s.valid || 0} / ${s.failed || 0}`,r.error || `${s.cases || 0}件を処理 · ${r.state}`],
    ['基準からの改善量',signed(delta),comp.compatible?`共通${comp.pairs.size}件・両方成功${valid.length}件／勝${valid.filter(p=>p.delta>0).length} 引分${valid.filter(p=>p.delta===0).length} 負${valid.filter(p=>p.delta<0).length}`:b?comp.reason:'比較する基準の版を選べます'],
    ['平均実行時間',`${num(s.seconds_mean,3)} 秒`,`最大 ${num(s.seconds_max,3)} 秒 · 子プロセス起動を含むローカル計測`]
  ].map(([t,v,n])=>`<div class="card"><div class="title">${esc(t)}</div><div class="value">${esc(v)}</div><small>${esc(n)}</small></div>`).join('');
  const comparable=runs.filter(x=>x.state==='complete' && x.summary?.failed===0 && x.summary?.cases>0 && safeValue(x.summary?.score_sum) && x.suite_signature===r.suite_signature && x.evaluator_signature===r.evaluator_signature).sort((a,b)=>(b.summary.score_sum-a.summary.score_sum)*(r.direction==='max'?1:-1));
  $('history').innerHTML=runs.map(x=>{
    const xs=x.summary || {}, rank=comparable.findIndex(y=>y.id===x.id);
    return `<tr class="${x.id===chosen?'selected':''}"><td>${rank>=0?rank+1:'—'}</td><td class="run-label">${esc(x.label || 'メモなし')}<small>${esc(x.id)} · ${esc(x.source_sha256?.slice(0,12) || '')}</small></td><td>${xs.cases || 0}</td><td>${xs.valid || 0} / ${xs.failed || 0}</td><td>${x.state==='complete' && xs.failed===0 ? num(xs.score_sum):'—'}</td><td>${num(xs.seconds_mean,3)}</td><td>${esc(x.state)} ${x.error?logLink(x,null,'build.stderr.txt','ビルドログ'):''}</td></tr>`;
  }).join('');
  const previous=$('feature').value;
  const defs=r.config?.features || [];
  $('feature').innerHTML=defs.length?defs.map(f=>`<option>${esc(f.name)}</option>`).join(''):'<option value="">分類設定なし</option>';
  if(defs.some(f=>f.name===previous)) $('feature').value=previous;
  const feature=$('feature').value, groups=new Map();
  for(const row of r.rows) {
    const f=row.features[feature], name=f?.group || '全体';
    if(!groups.has(name)) groups.set(name,{name,index:f?.index || 0,rows:[]});
    groups.get(name).rows.push(row);
  }
  const grouped=[...groups.values()].sort((a,b)=>a.index-b.index);
  $('groups').innerHTML=grouped.map(g=>{
    const vs=g.rows.filter(x=>x.status==='ok'), ps=g.rows.map(x=>comp.pairs.get(x.id)).filter(p=>p?.delta!=null), percentages=ps.map(p=>p.percent).filter(p=>p!=null);
    g.percent=mean(percentages); g.score=mean(vs.map(x=>x.score));
    return `<tr><td>${esc(g.name)}</td><td>${g.rows.length}</td><td>${vs.length} / ${g.rows.length-vs.length}</td><td>${num(g.score)}</td><td>${ps.length}（率 ${percentages.length}件）</td><td class="${tone(g.percent)}">${signed(g.percent)}${g.percent!=null?'%':''}</td><td>${num(mean(g.rows.map(x=>x.seconds)),3)}</td></tr>`;
  }).join('');
  renderChart(grouped,comp.compatible);
  const filter=$('filter').value;
  $('cases').innerHTML=r.rows.filter(row=>filter==='all' || (filter==='failed'?row.status!=='ok':comp.pairs.get(row.id)?.delta<0)).map(row=>{
    const p=comp.pairs.get(row.id), cat=row.features[feature]?.group || '—';
    return `<tr><td>${esc(row.id)}</td><td>${esc(cat)}</td><td>${num(row.score)}</td><td class="${tone(p?.delta)}">${signed(p?.delta)}</td><td class="${tone(p?.percent)}">${signed(p?.percent)}${p?.percent!=null?'%':''}</td><td>${num(row.seconds,3)}</td><td title="${esc(row.message || '')}"><span class="${row.status==='ok'?'good':'bad'}">${esc(row.status)}</span><span class="log-links">${logLink(r,row,'solver.stderr.txt','実行')}${logLink(r,row,r.config?.mode==='interactive' && !r.config?.judge_command?'solver.stderr.txt':'judge.stdout.txt','採点')}${logLink(r,row,'output.txt','出力')}</span>${row.warnings?.length?' ⚠ 分類取得不可':''}</td></tr>`;
  }).join('');
}
function renderChart(groups, compared) {
  const key=compared?'percent':'score', vals=groups.map(g=>g[key]).filter(x=>x!=null);
  if(!vals.length){$('chart').textContent=compared?'比較可能な得点がありません':'分類するパラメータは設定ファイルで追加できます';return;}
  const w=1000, rowH=46, h=groups.length*rowH+38, max=Math.max(...vals.map(Math.abs),1), center=compared?540:260, span=compared?350:620;
  let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${compared?'分類ごとの平均改善率':'分類ごとの平均生得点'}"><text x="0" y="15" class="chart-title">${compared?'基準に対する平均改善率（右が改善）':'平均生得点（入力の難しさによって尺度が変わります）'}</text><line x1="${center}" y1="28" x2="${center}" y2="${h}" stroke="#b9cdc0"/>`;
  groups.forEach((g,i)=>{
    const v=g[key], y=35+i*rowH, width=v==null?0:Math.abs(v)/max*span, x=v<0?center-width:center;
    svg+=`<text x="0" y="${y+19}" fill="#536d64" font-size="13">${esc(g.name)}</text><rect x="${x}" y="${y}" width="${width}" height="27" rx="4" fill="${v<0?'#cf7968':'#439b76'}"/><text x="${Math.min(940,center+span+14)}" y="${y+19}" fill="#536d64" font-size="12" text-anchor="end">${esc(compared?signed(v):num(v))}${compared && v!=null?'%':''}</text>`;
  });
  $('chart').innerHTML=svg+'</svg>';
}
async function refresh(){try{state=await api('/api/state');render();}catch(e){error(e);}}
async function startRun(count,submission){try{error(null);const r=await api('/api/run',{count,label:$('label').value,...(submission?{submission}:{})});chosen=r.id;pendingId=r.id;selectionMade=false;await refresh();}catch(e){error(e);}}
for(const n of [10,100]) $('run'+n).onclick=()=>startRun(n);
$('submissions').onclick=event=>{const b=event.target.closest('button[data-submission]');if(b && !b.disabled) startRun(Number(b.dataset.count),b.dataset.submission);};
$('stop').onclick=async()=>{try{await api('/api/stop',{});await refresh();}catch(e){error(e);}};
$('freeze').onclick=async()=>{
  freezing=true; $('freeze').disabled=true;
  try {
    error(null);
    const saved=await api('/api/freeze',{label:$('label').value});
    $('freeze-status').textContent=`${saved.filename} を保存しました。${saved.matching_runs.length?'同じソースのテスト記録があります。':'同じソースのテスト記録はありません。'}`;
    await refresh();
  } catch(e){error(e);} finally {freezing=false;$('freeze').disabled=false;}
};
$('current').onchange=()=>{chosen=$('current').value;pendingId='';selectionMade=false;render();};
$('baseline').onchange=()=>{base=$('baseline').value;selectionMade=true;render();};
$('feature').onchange=render;
$('filter').onchange=render;
refresh(); setInterval(refresh,1800);
