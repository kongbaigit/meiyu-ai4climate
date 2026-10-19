(() => {
  'use strict';
  const INPUT = MEIYU_DECISION_INPUT, $ = id => document.getElementById(id);
  const HOUR = 3600000, DAY = 24 * HOUR, KEY = 'meiyu-decision-v1-';
  const hasHTTP = /^https?:$/.test(location.protocol), clock = () => Date.now();
  let isServer=false,workerRunning=false;
  const state = {mode:'live', location:'hangzhou', weather:{}, selected:null, busy:false, result:null, eligibility:null, sequence:0};
  let aborter = null;
  const money = n => new Intl.NumberFormat('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}).format(n);
  const percent = p => `${(p*100).toFixed(1)}%`;
  const localTime = value => new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value));
  const shortDate = value => new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric'}).format(new Date(value));
  const text = (id,value) => { $(id).textContent = value; };
  const sha = async raw => [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw)))].map(x=>x.toString(16).padStart(2,'0')).join('');
  const finite = value => typeof value==='number' && Number.isFinite(value);
  const utcISO = ms => new Date(ms).toISOString().replace('.000Z','Z');
  function windowSpecs(at=clock()) {
    const d = new Date(at+8*HOUR), first = Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate()+1);
    return Array.from({length:7},(_,i)=>({start_utc:utcISO(first+i*DAY),end_utc:utcISO(first+(i+1)*DAY)}));
  }
  function requestURL(key,windows) {
    const loc=INPUT.locations[key];
    const q=new URLSearchParams({latitude:String(loc.latitude),longitude:String(loc.longitude),models:INPUT.model,hourly:'precipitation',start_hour:new Date(Date.parse(windows[0].start_utc)+HOUR).toISOString().slice(0,16),end_hour:windows[6].end_utc.slice(0,16),timezone:'UTC',timeformat:'iso8601',precipitation_unit:'mm',cell_selection:'nearest'});
    return 'https://ensemble-api.open-meteo.com/v1/ensemble?'+q;
  }
  function apiHour(value) {
    if(typeof value!=='string' || !/^\d{4}-\d\d-\d\dT\d\d:00(?::00)?(?:Z|\+00:00)?$/.test(value)) throw Error('响应时间不是整点UTC。');
    const ms=Date.parse(/Z$|\+00:00$/.test(value)?value:value+'Z');
    if(!Number.isFinite(ms)) throw Error('响应时间无效。');
    return ms;
  }
  async function parseRaw(raw,key,fetched,windows,url) {
    const b=JSON.parse(raw), loc=INPUT.grids[key], n=INPUT.expected_members;
    if(!b || Array.isArray(b) || b.error) throw Error('天气接口返回错误。');
    if(b.latitude!==loc.latitude || b.longitude!==loc.longitude) throw Error('响应网格不符，未替换缓存。');
    if(b.utc_offset_seconds!==0 || !['GMT','UTC'].includes(b.timezone)) throw Error('响应不是UTC。');
    if(windows.length!==7 || windows.some((w,i)=>Date.parse(w.end_utc)-Date.parse(w.start_utc)!==DAY || (i>0&&w.start_utc!==windows[i-1].end_utc))) throw Error('24小时窗口无效。');
    if(url!==requestURL(key,windows)) throw Error('请求来源或窗口不符。');
    const h=b.hourly,u=b.hourly_units;
    if(!h || !u || !Array.isArray(h.time) || (u.time!==undefined&&u.time!=='iso8601')) throw Error('小时字段缺失或单位错误。');
    if(u.precipitation!==undefined&&u.precipitation!=='mm') throw Error('降水单位错误。');
    const expected=new Set(windows.flatMap(w=>Array.from({length:24},(_,j)=>Date.parse(w.start_utc)+(j+1)*HOUR)));
    const times=h.time.map(apiHour);
    if(new Set(times).size!==times.length || times.some(t=>!expected.has(t))) throw Error('小时重复或超出窗口。');
    const perturbed=Object.keys(h).filter(k=>/^precipitation_member\d+$/.test(k));
    const allowed=['precipitation',...Array.from({length:n-1},(_,i)=>'precipitation_member'+String(i+1).padStart(2,'0'))];
    if(perturbed.some(k=>!allowed.includes(k))) throw Error('集合成员身份不符。');
    const fields=[...(Object.hasOwn(h,'precipitation')?['precipitation']:[]),...perturbed];
    const values={};
    for(const k of fields) {
      if(u[k]!=='mm'||!Array.isArray(h[k])||h[k].length>times.length) throw Error('成员单位或长度错误。');
      if(h[k].some(x=>x!==null&&(!finite(x)||x<0))) throw Error('降水含无效值。');
      values[k]=new Map(h[k].map((v,i)=>[times[i],v]));
    }
    const rows=windows.map(w=>{
      const required=Array.from({length:24},(_,i)=>Date.parse(w.start_utc)+(i+1)*HOUR), totals=[],counts=[];
      for(const k of allowed) {
        const vals=required.map(t=>values[k]?.get(t)).filter(finite);counts.push(vals.length);
        if(vals.length===24) totals.push(vals.reduce((a,b)=>a+b,0));
      }
      totals.sort((a,b)=>a-b);
      const complete=totals.length===n&&Math.min(...counts)===24,events=totals.length?totals.filter(x=>x>=25).length:null;
      const median=totals.length?(totals[Math.floor((totals.length-1)/2)]+totals[Math.ceil((totals.length-1)/2)])/2:null;
      const rounded=x=>x===null?null:Math.round((x+Number.EPSILON)*1000)/1000;
      return {...w,probability:complete?events/n:null,complete,members_valid:totals.length,members_expected:n,hours_min:Math.min(...counts),hours_expected:24,event_members:events,rain_median_mm:rounded(median),rain_min_mm:rounded(totals.length?totals[0]:null),rain_max_mm:rounded(totals.length?totals.at(-1):null)};
    });
    return {schema_version:1,location_key:key,location:INPUT.locations[key],source:INPUT.source,request_url:url,fetched_at_utc:fetched,raw_sha256:await sha(raw),probability_kind:'ensemble_member_fraction_uncalibrated',event_threshold_mm:25,expected_members:n,windows:rows};
  }
  function resultStatus(snapshot,error=null) {
    if(!snapshot) return {status:error?'error':'missing',snapshot:null,error};
    const age=clock()-Date.parse(snapshot.fetched_at_utc);
    const validTime=Number.isFinite(age)&&age>=-300000&&age<=3*HOUR;
    return {status:!validTime?'stale':snapshot.windows.every(w=>w.complete)?'fresh':'partial',snapshot,error};
  }
  async function loadLocal(key) {
    try {
      const packed=JSON.parse(localStorage.getItem(KEY+key)||'null');
      if(!packed)return null;
      const s=packed.snapshot, parsed=await parseRaw(packed.raw,key,s.fetched_at_utc,s.windows.map(w=>({start_utc:w.start_utc,end_utc:w.end_utc})),s.request_url);
      if(JSON.stringify(parsed)!==JSON.stringify(s))throw Error('本地缓存摘要或内容不符。');
      return resultStatus(parsed);
    } catch { return null; }
  }
  function currentWindow() {
    if(state.mode==='demo')return {start_utc:null,end_utc:null,probability:.6,complete:true,members_valid:null,members_expected:null,hours_min:null,hours_expected:null,rain_median_mm:null};
    return state.weather[state.location]?.snapshot?.windows.find(w=>w.start_utc===state.selected)||null;
  }
  function eligibility() {
    if(state.mode==='demo') return {ok:true,reason:'算账示例，概率60%为设定值。'};
    const data=state.weather[state.location],s=data?.snapshot,w=currentWindow();
    if(!s||!w) return {ok:false,reason:state.busy?'正在获取完整天气。':'尚无有效天气，请联网更新。'};
    const age=clock()-Date.parse(s.fetched_at_utc);
    if(!Number.isFinite(age)||age< -300000||age>3*HOUR)return {ok:false,reason:'天气已过期，请更新后再计算。'};
    if(s.location_key!==state.location||s.probability_kind!=='ensemble_member_fraction_uncalibrated'||s.event_threshold_mm!==25||s.expected_members!==INPUT.expected_members)return {ok:false,reason:'天气来源或概率口径不符。'};
    const start=Date.parse(w.start_utc),end=Date.parse(w.end_utc);
    if(!Number.isFinite(start)||end-start!==DAY||start<=clock()||!windowSpecs().some(spec=>spec.start_utc===w.start_utc))return {ok:false,reason:'所选窗口已不属于当前未来7日，请更新天气。'};
    if(!w.complete||w.members_valid!==INPUT.expected_members||w.members_expected!==INPUT.expected_members||w.hours_min!==24||w.hours_expected!==24||!finite(w.probability)||w.probability<0||w.probability>1)return {ok:false,reason:'成员或小时不完整，暂停搬货建议。'};
    return {ok:true,reason:'按集合情景估计和你的成本假设计算。'};
  }
  function readCosts() {
    const entries=[['move_cost','move-cost','搬货成本'],['loss_without','loss-without','不搬预计损失'],['loss_after','loss-after','搬后预计损失']];
    return Object.fromEntries(entries.map(([key,id,label])=>{const raw=$(id).value.trim(),n=raw===''?NaN:Number(raw);if(!finite(n)||n<0||n>1e9)throw Error(label+'请填写0至10亿元之间的有效金额。');return [key,n];}));
  }
  function renderCalculation() {
    const gate=eligibility();state.eligibility=gate;state.result=null;
    let costs,error=null;
    try{costs=readCosts();}catch(e){error=e.message;}
    text('residual-summary',costs?money(costs.loss_after)+'元':'待填写');
    $('input-error').hidden=!error;text('input-error',error||'');
    let pending=error||(!gate.ok?gate.reason:!$('assumptions').checked?'确认成本假设后，自动比较两种选择。':null);
    const card=$('result-card');card.className='result-card';
    for(const id of ['choice-move','choice-keep'])$(id).classList.remove('winner');
    text('result-kicker',state.mode==='demo'?'算账示例 · 非当前天气':'按你的设定计算 · 情景建议');
    if(pending) {
      card.classList.add('pending');text('result-title',!gate.ok?'暂不计算搬货结论':error?'请核对金额':'先确认成本假设');text('result-subtitle',pending);text('result-icon','—');
      for(const id of ['expected-without','expected-move','benefit'])text(id,'—');
      text('benefit-label','两种选择的成本差');text('threshold-text','缺数据、过期或未确认时，不给行动结论。');text('without-formula','降雨事件估计 × 不搬预计损失');text('move-formula','搬货成本 + 搬后预计货损');
      $('download-record').disabled=true;
    } else {
      const w=currentWindow(),r=MeiyuDecision.calculate({probability:w.probability,...costs});state.result=r;
      const titles={move:'按当前设定，建议搬货',keep:'按当前设定，暂不搬',tie:'两种选择的预计成本相同'};
      text('result-title',titles[r.state]);text('result-icon',r.state==='move'?'↗':r.state==='keep'?'→':'＝');card.classList.add(r.state);
      if(r.state!=='tie')$('choice-'+(r.state==='move'?'move':'keep')).classList.add('winner');
      text('result-subtitle',state.mode==='demo'?'这是概率60%的算账示例，修改金额可观察结果变化。':'基于尚未校准的集合情景估计；真实货损仍取决于你的现场条件。');
      text('expected-without','¥ '+money(r.expected_without));text('expected-move','¥ '+money(r.expected_move));
      text('without-formula',percent(r.probability)+' × '+money(r.loss_without));text('move-formula',money(r.move_cost)+' + '+percent(r.probability)+' × '+money(r.loss_after));
      text('benefit-label',r.state==='tie'?'两种选择的成本差':(r.state==='move'?'搬货':'不搬')+'的预计总成本更低');text('benefit','¥ '+money(Math.abs(r.benefit)));
      const threshold=r.break_even_probability;
      text('threshold-text',threshold===null?'当前设定中，搬货没有降低事件发生时的货损。':threshold>1?'搬货成本超过可避免的事件损失。':'按这些金额，临界降雨事件估计为 '+percent(threshold)+'。');
      $('download-record').disabled=false;
    }
    text('actions-title',state.result?.state==='keep'?'暂不搬，也留下一次记录':state.result?.state==='move'?'搬之前，确认这三件事':'确认这次怎么处理');
  }
  function renderWeather() {
    const demo=state.mode==='demo',data=state.weather[state.location],s=data?.snapshot,w=currentWindow();
    $('demo-banner').hidden=!demo;$('location').disabled=demo;$('window').disabled=demo;$('refresh').disabled=state.busy||demo;
    for(const mode of ['live','demo']){$('mode-'+mode).classList.toggle('selected',state.mode===mode);$('mode-'+mode).setAttribute('aria-pressed',String(state.mode===mode));}
    text('probability-label',demo?'算账示例的降雨事件概率':'达到参考降雨阈值的成员占比');
    text('probability-value',finite(w?.probability)?percent(w.probability):'—');text('probability-note',demo?'演示设定 · 不代表当前天气':'未经校准的集合情景估计');
    text('rain-value',!demo&&finite(w?.rain_median_mm)?w.rain_median_mm.toFixed(1)+' mm':'—');
    text('coverage-value',!demo&&w?`${w.members_valid} / ${w.members_expected}`:'—');text('coverage-note',!demo&&w?`最少 ${w.hours_min} / 24 小时 · ${w.complete?'完整':'不完整'}`:'成员数 / 预期成员数');
    text('source-time',demo?'算账示例，无获取时刻':s?localTime(s.fetched_at_utc)+'（北京时间）':'—');text('source-window',demo?'示例不对应真实天气窗口':w?localTime(w.start_utc)+' 至 '+localTime(w.end_utc):'—');text('source-sha',demo?'示例无原始响应':s?.raw_sha256||'—');$('source-url').href=!demo&&s?.request_url?s.request_url:'https://open-meteo.com/en/docs/ensemble-api';
    let status;
    if(demo) status='示例模式：不会把假设概率用作最新天气。';
    else if(state.busy)status='正在核对最新天气…';
    else if(!s)status='获取未完成：'+(data?.error||'当前没有有效缓存');
    else {
      const age=clock()-Date.parse(s.fetched_at_utc),stale=!Number.isFinite(age)||age>3*HOUR||age< -300000;
      status=(stale?'已过期 · ':data?.error?'更新失败，保留上次数据 · ':'已获取 · ')+localTime(s.fetched_at_utc)+' 北京时间';
    }
    text('weather-status',status);$('weather-status').classList.toggle('error',!demo&&(!s||!!data?.error||!eligibility().ok));
    const week=$('week');week.replaceChildren();
    if(!demo)for(const row of s?.windows||[]) {
      if(Date.parse(row.start_utc)<=clock())continue;
      const button=document.createElement('button');button.className='day'+(row.start_utc===state.selected?' selected':'');button.type='button';button.setAttribute('aria-pressed',String(row.start_utc===state.selected));
      const date=document.createElement('span');date.textContent=shortDate(row.start_utc)+' 08:00起';const p=document.createElement('b');p.textContent=finite(row.probability)?percent(row.probability):'缺数据';const rain=document.createElement('small');rain.textContent=finite(row.rain_median_mm)?'中位雨量 '+row.rain_median_mm.toFixed(1)+' mm':'不计算累计';const bar=document.createElement('i'),fill=document.createElement('span');fill.style.width=finite(row.probability)?(row.probability*100)+'%':'0%';bar.append(fill);button.append(date,p,rain,bar);button.addEventListener('click',()=>{state.selected=row.start_utc;$('window').value=state.selected;resetActions();render();});week.append(button);
    }
  }
  function render(){renderWeather();renderCalculation();}
  function updateWindowOptions() {
    const select=$('window'),s=state.weather[state.location]?.snapshot;
    select.replaceChildren();
    const future=(s?.windows||[]).filter(w=>Date.parse(w.start_utc)>clock());
    if(!future.length){const option=new Option('尚无完整未来窗口','');select.add(option);state.selected=null;return;}
    if(!future.some(w=>w.start_utc===state.selected))state.selected=future[0].start_utc;
    for(const w of future) select.add(new Option(`${shortDate(w.start_utc)} 08:00 至 ${shortDate(w.end_utc)} 08:00${w.complete?'':' · 不完整'}`,w.start_utc));
    select.value=state.selected;
  }
  function resetActions(){for(const id of ['action-1','action-2','action-3'])$(id).checked=false;}
  async function refresh(force=false) {
    if(state.mode==='demo')return;
    const key=state.location,seq=++state.sequence;
    if(aborter)aborter.abort();aborter=new AbortController();const controller=aborter,signal=controller.signal;
    state.busy=true;render();const timeout=setTimeout(()=>controller.abort(),45000);
    try {
      let data;
      if(isServer) {
        const response=await fetch(`/api/decision-weather?location=${key}${force?'&force=1':''}`,{signal,cache:'no-store'});
        if(!response.ok)throw Error('天气服务暂不可用（'+response.status+'）。');
        data=await response.json();
        if(!data||!['fresh','stale','partial','missing','error'].includes(data.status))throw Error('天气服务返回格式不符。');
      } else {
        const old=state.weather[key]?.snapshot,age=old?clock()-Date.parse(old.fetched_at_utc):Infinity;
        if(!force&&age>=0&&age<HOUR&&old.windows.some(w=>Date.parse(w.start_utc)===Date.parse(windowSpecs()[0].start_utc)))data=resultStatus(old);
        else {
          const windows=windowSpecs(),url=requestURL(key,windows),response=await fetch(url,{signal,cache:'no-store'});
          if(!response.ok)throw Error('公开天气接口返回 '+response.status+'。');
          const raw=await response.text();if(raw.length>8*1024*1024)throw Error('天气响应过大。');
          const snapshot=await parseRaw(raw,key,new Date().toISOString().replace('.000Z','Z'),windows,url);
          if(old&&old.windows.length===7&&old.windows.every(w=>w.complete)&&!snapshot.windows.every(w=>w.complete))throw Error('新响应缺少成员或小时，保留上次完整数据。');
          data=resultStatus(snapshot);
          try{localStorage.setItem(KEY+key,JSON.stringify({snapshot,raw}));}catch{}
        }
      }
      state.weather[key]=data;
    } catch(error) {
      if(seq!==state.sequence)return;
      state.weather[key]=resultStatus(state.weather[key]?.snapshot||null,error.name==='AbortError'?'连接超时或已取消。':error.message);
    } finally {
      clearTimeout(timeout);
      if(seq===state.sequence){state.busy=false;updateWindowOptions();render();}
    }
  }
  function exportRecord() {
    renderCalculation();if(!state.result)return;
    const data=state.weather[state.location],w=currentWindow();
    const record={schema_version:1,created_at_utc:new Date().toISOString(),mode:state.mode,location_key:state.mode==='live'?state.location:null,assumptions_confirmed:true,loss_definition:'降雨事件发生时考虑可能不受损后的条件平均损失；不是整批货物价值。',probability_kind:state.mode==='demo'?'hypothetical_demo':'ensemble_member_fraction_uncalibrated',fetched_at_utc:state.mode==='live'?data.snapshot.fetched_at_utc:null,raw_sha256:state.mode==='live'?data.snapshot.raw_sha256:null,request_url:state.mode==='live'?data.snapshot.request_url:null,window:state.mode==='live'?w:null,calculation:state.result,actions:Object.fromEntries(['action-1','action-2','action-3'].map(id=>[id,$(id).checked])),limitations:'情景估算，非货损概率预测或已实现收益。'};
    const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='梅雨有数_搬货账单.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
  }
  async function referenceStatus() {
    if(!isServer)return;
    try{const r=await fetch('/api/reference-status?location='+state.location,{cache:'no-store'});if(!r.ok)return;const d=await r.json();text('reference-status',d.summary||'站点参考数据尚未获取；后台会按日核查。');}catch{}
  }
  for(const id of ['move-cost','loss-without','loss-after','assumptions'])$(id).addEventListener('input',()=>{resetActions();renderCalculation();});
  $('location').addEventListener('change',()=>{state.location=$('location').value;state.selected=null;$('assumptions').checked=false;resetActions();updateWindowOptions();refresh();referenceStatus();});
  $('window').addEventListener('change',()=>{state.selected=$('window').value;resetActions();render();});
  $('refresh').addEventListener('click',()=>refresh(true));
  for(const mode of ['live','demo'])$('mode-'+mode).addEventListener('click',()=>{state.mode=mode;$('assumptions').checked=false;resetActions();render();if(mode==='live')refresh();});
  $('apply-labor').addEventListener('click',()=>{
    try{const vals=['labor-people','labor-minutes','labor-rate','labor-other'].map(id=>{const raw=$(id).value.trim(),v=raw===''?NaN:Number(raw);if(!finite(v)||v<0)throw Error('人工估算请填写有效非负数字。');return v;});const amount=vals[0]*vals[1]/60*vals[2]+vals[3];if(!finite(amount)||amount>1e9||vals[0]<1)throw Error('人工估算金额或人数超出范围。');$('move-cost').value=amount.toFixed(2);$('assumptions').checked=false;renderCalculation();}catch(e){text('input-error',e.message);$('input-error').hidden=false;}
  });
  $('download-record').addEventListener('click',exportRecord);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'){updateWindowOptions();render();refresh();}});
  setInterval(()=>{updateWindowOptions();render();},60000);
  setInterval(()=>{refresh();referenceStatus();},HOUR);
  window.MEIYU_DECISION_APP={state,render,eligibility,windowSpecs,parseRaw,requestURL,refresh,exportRecord};
  (async()=>{
    if(hasHTTP)try{const response=await fetch('/api/health',{cache:'no-store',signal:AbortSignal.timeout(3000)});if(response.ok){const health=await response.json();isServer=health.status==='ok'&&!!health.worker;workerRunning=isServer&&health.worker.running===true;}}catch{}
    for(const key of Object.keys(INPUT.locations)){const local=await loadLocal(key);state.weather[key]=local||INPUT.weather_seed[key]||{status:'missing',snapshot:null,error:null};}
    text('service-mode',workerRunning?'服务运行时按小时检查':'打开时联网获取');
    text('update-explanation',workerRunning?'页面打开时自动检查；后台服务每小时刷新两地天气，网页关闭后仍运行。电脑和服务需要保持开启。':'当前未连接常驻后台。打开时自动联网，页面保持打开时每小时检查；关闭页面后不会继续获取。运行start.cmd可启用后台服务。');
    updateWindowOptions();render();refresh();referenceStatus();
  })();
})();
