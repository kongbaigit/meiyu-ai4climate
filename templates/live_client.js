(()=>{
'use strict';
const boot=DATA.live,DAY=86400000,HOUR=3600000,products=['forecast','archive','station'];
if(!boot)return;
const el=id=>document.getElementById(id),safe=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pad=n=>String(n).padStart(2,'0'),isoDay=t=>new Date(t).toISOString().slice(0,10),stamp=t=>new Date(t).toISOString().replace('.000Z','Z');
const numeric=v=>typeof v==='number'&&Number.isFinite(v),positive=v=>numeric(v)&&v>=0&&v<9990;
const dateLabel=s=>s?s.replaceAll('-','.'):'—';
const localTime=s=>s?new Date(s).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'—';
function utcDay(now){const d=new Date(now);return Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate())}
function dateRange(first,last){const out=[];for(let d=first;d<=last;d+=DAY)out.push(isoDay(d));return out}
function request(key,product,now=Date.now()){
 const location=boot.locations[key];if(!location||!products.includes(product))throw Error('未知位置或数据类型。');
 const today=utcDay(now);let first,last,url;
 if(product==='forecast'){
  first=today+DAY;last=today+7*DAY;
  url=new URL('https://api.open-meteo.com/v1/forecast');
  Object.entries({latitude:location.latitude,longitude:location.longitude,hourly:'precipitation,temperature_2m,relative_humidity_2m',models:'ecmwf_ifs025',timezone:'UTC',temperature_unit:'celsius',precipitation_unit:'mm',timeformat:'iso8601',forecast_days:9}).forEach(([k,v])=>url.searchParams.set(k,v));
 }else if(product==='archive'){
  last=today-7*DAY;first=Date.UTC(new Date(last).getUTCFullYear(),0,1);
  url=new URL('https://archive-api.open-meteo.com/v1/archive');
  Object.entries({latitude:location.latitude,longitude:location.longitude,start_date:isoDay(first),end_date:isoDay(last),daily:'precipitation_sum,temperature_2m_mean',models:'era5',timezone:'UTC',temperature_unit:'celsius',precipitation_unit:'mm',timeformat:'iso8601'}).forEach(([k,v])=>url.searchParams.set(k,v));
 }else{
  first=Date.UTC(new Date(today).getUTCFullYear(),0,1);last=today-DAY;
  url=new URL(`https://www.ncei.noaa.gov/oa/synoptic-summary-of-the-day/v2/access/by-year/${new Date(today).getUTCFullYear()}/csv/SSOD_${location.station_id}_${new Date(today).getUTCFullYear()}.csv`);
 }
 return {product,location:{...location,key},request_url:url.href,start_date:isoDay(first),end_date:isoDay(last),dates:dateRange(first,last)};
}
function parseCSV(raw){
 const rows=[];let row=[],field='',quoted=false;
 for(let i=0;i<raw.length;i++){
  const c=raw[i];if(c==='"'){if(quoted&&raw[i+1]==='"'){field+='"';i++}else quoted=!quoted}
  else if(c===','&&!quoted){row.push(field);field=''}
  else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&raw[i+1]==='\n')i++;row.push(field);if(row.some(x=>x!==''))rows.push(row);row=[];field=''}else field+=c;
 }
 if(quoted)throw Error('CSV引号未闭合。');if(field||row.length){row.push(field);rows.push(row)}
 if(rows.length<2)throw Error('站点文件没有记录。');const headers=rows.shift();headers[0]=headers[0].replace(/^\ufeff/,'');
 if(new Set(headers).size!==headers.length)throw Error('CSV字段重复。');
 return rows.map(r=>{if(r.length!==headers.length)throw Error('CSV行字段数不一致。');return Object.fromEntries(headers.map((h,i)=>[h,r[i]]))});
}
function normalize(raw,req,fetched){
 const rows=[],location=req.location;let grid={latitude:location.latitude,longitude:location.longitude},lastReported=null;
 const baseRow=date=>({date,start_utc:date+'T00:00:00Z',end_utc:stamp(Date.parse(date+'T00:00:00Z')+DAY),rain_mm:null,temperature_mean_c:null,humidity_mean_pct:null,hours_present:null,hours_expected:null,status:'missing',reason:'缺少完整降水数据'});
 if(req.product==='station'){
  const source=parseCSV(raw),map=new Map();
  const needed=['STATION','DATE','LATITUDE','LONGITUDE','total_precipitation','total_precipitation_Measurement_Code'];
  if(!needed.every(k=>k in source[0]))throw Error('站点字段缺失。');
  for(const r of source){
   if(r.STATION!==location.station_id)throw Error('站点身份不符。');
   if(!/^\d{4}-\d{2}-\d{2}$/.test(r.DATE)||isoDay(Date.parse(r.DATE+'T00:00:00Z'))!==r.DATE||r.DATE.slice(0,4)!==req.start_date.slice(0,4))throw Error('站点日期不合法。');
   if(map.has(r.DATE))throw Error('站点日期重复。');
   const lat=Number(r.LATITUDE),lon=Number(r.LONGITUDE);
   if(!r.LATITUDE.trim()||!r.LONGITUDE.trim()||!numeric(lat)||!numeric(lon)||Math.abs(lat-location.latitude)>.1||Math.abs(lon-location.longitude)>.1)throw Error('站点坐标不符。');
   map.set(r.DATE,r);if(r.DATE<=req.end_date&&(!lastReported||r.DATE>lastReported))lastReported=r.DATE;
  }
  for(const date of req.dates){const out=baseRow(date),r=map.get(date);if(r){const rain=r.total_precipitation.trim()===''?null:Number(r.total_precipitation),code=r.total_precipitation_Measurement_Code.trim().toUpperCase();if(positive(rain)&&['D','F','G','24'].includes(code)){out.rain_mm=rain;out.status='complete';out.reason=''}else{out.status='partial';out.reason='报告测量码或降水总量不满足完整日要求'}}rows.push(out)}
 }else{
  let body;try{body=JSON.parse(raw)}catch{throw Error('接口未返回有效JSON。')}
  if(!body||typeof body!=='object'||Array.isArray(body)||body.error)throw Error('接口返回错误或结构异常。');
  if(body.utc_offset_seconds!==0)throw Error('响应不是UTC日界。');
  if(!numeric(body.latitude)||!numeric(body.longitude)||Math.abs(body.latitude-location.latitude)>.3||Math.abs(body.longitude-location.longitude)>.3)throw Error('返回格点不匹配。');
  grid={latitude:body.latitude,longitude:body.longitude};
  const hourly=req.product==='forecast',data=body[hourly?'hourly':'daily'],units=body[hourly?'hourly_units':'daily_units'];
  const vars=hourly?['precipitation','temperature_2m','relative_humidity_2m']:['precipitation_sum','temperature_2m_mean'];
  if(!data||!units||units[vars[0]]!=='mm'||units[vars[1]]!=='°C'||(hourly&&units[vars[2]]!=='%'))throw Error('降水、温度或湿度单位不符。');
  if(!Array.isArray(data.time)||!data.time.length||vars.some(v=>!Array.isArray(data[v])||data[v].length!==data.time.length))throw Error('接口字段长度不一致。');
  const map=new Map();
  data.time.forEach((time,i)=>{
   const pattern=hourly?/^\d{4}-\d{2}-\d{2}T\d{2}:00$/:/^\d{4}-\d{2}-\d{2}$/;
   if(typeof time!=='string'||!pattern.test(time))throw Error('时间不是UTC整点或自然日。');
   const millis=Date.parse(time+(hourly?':00Z':'T00:00:00Z'));
   if(!Number.isFinite(millis)||new Date(millis).toISOString().slice(0,hourly?16:10)!==time)throw Error('接口时间无效。');
   if(map.has(millis))throw Error('接口时间重复。');
   const vals=vars.map(v=>data[v][i]);
   if(vals.some(v=>v!==null&&!numeric(v)))throw Error('响应包含非数值数据。');
   if(vals[0]!==null&&!positive(vals[0]))throw Error('降水为负或超出范围。');
   if(hourly&&vals[2]!==null&&(vals[2]<0||vals[2]>100))throw Error('相对湿度超出0—100。');
   map.set(millis,vals);
  });
  for(const date of req.dates){
   const out=baseRow(date),start=Date.parse(date+'T00:00:00Z');
   if(hourly){
    out.hours_expected=24;const vals=Array.from({length:24},(_,i)=>map.get(start+(i+1)*HOUR));
    out.hours_present=vals.filter(v=>v&&positive(v[0])).length;
    if(out.hours_present===24){out.rain_mm=Math.round(vals.reduce((s,v)=>s+v[0],0)*10000)/10000;out.status='complete';out.reason=''}else if(out.hours_present)out.status='partial';
    const avg=(col,valid)=>vals.every(v=>v&&valid(v[col]))?Math.round(vals.reduce((s,v)=>s+v[col],0)/24*10000)/10000:null;
    out.temperature_mean_c=avg(1,numeric);out.humidity_mean_pct=avg(2,v=>numeric(v)&&v>=0&&v<=100);
   }else{const v=map.get(start);if(v&&positive(v[0])){out.rain_mm=v[0];out.status='complete';out.reason=''}if(v&&numeric(v[1]))out.temperature_mean_c=v[1]}
   rows.push(out);
  }
  if(!rows.some(r=>r.status==='complete'))throw Error('响应没有完整降水窗口，保留原有效缓存。');
 }
 const complete=rows.filter(r=>r.status==='complete');
 return {schema_version:1,product:req.product,location,fetched_at_utc:fetched,request_url:req.request_url,grid,rows,
  source:{provider:req.product==='station'?'NOAA/NCEI':'Open-Meteo',kind:req.product==='forecast'?'数值预报':req.product==='archive'?'ERA5再分析背景':'SSOD站点派生参考',model:req.product==='forecast'?'ecmwf_ifs025':req.product==='archive'?'era5':'SSODv2',licence:req.product==='station'?'NOAA/NCEI公共数据，保留引用':'CC BY 4.0；免费接口仅限非商业使用'},
  coverage:{expected_days:rows.map(r=>r.date),complete_days:complete.map(r=>r.date),partial_days:rows.filter(r=>r.status==='partial').map(r=>r.date),missing_days:rows.filter(r=>r.status==='missing').map(r=>r.date),expected_day_count:rows.length,complete_day_count:complete.length,partial_day_count:rows.filter(r=>r.status==='partial').length,missing_day_count:rows.filter(r=>r.status==='missing').length,latest_available_date:complete.at(-1)?.date??null,last_reported_date:lastReported??rows.filter(r=>r.status!=='missing').at(-1)?.date??null}};
}
async function hash(text){if(!crypto?.subtle)throw Error('浏览器无法核对来源摘要，请使用HTTPS、本地HTTP或完整应用。');const raw=new TextEncoder().encode(text);return {raw_sha256:[...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(x=>pad(x.toString(16))).join(''),raw_bytes:raw.byteLength}}
let locationKey='hangzhou',busy=false;const memory={},errors={};
const storageKey=(key,product)=>`meiyu-weather-v1:${key}:${product}`;
function age(snapshot){return Math.max(0,(Date.now()-Date.parse(snapshot.fetched_at_utc))/HOUR)}
function stale(snapshot){return age(snapshot)>(snapshot.product==='forecast'?3:24)}
function badge(snapshot){const hours=age(snapshot);return `<span class="live-state-pill ${stale(snapshot)?'stale':''}">${stale(snapshot)?'缓存已过期':hours<.02?'刚刚获取':'缓存'} · ${hours<1?Math.floor(hours*60)+'分钟前':hours.toFixed(1)+'小时前'}</span>`}
async function loadStored(key,product){
 let packed=null;try{const value=localStorage.getItem(storageKey(key,product));if(value)packed=JSON.parse(value)}catch{}
 if(!packed)packed=boot.seed?.[key]?.[product]??null;
 if(!packed)return;
 try{
  if(typeof packed.raw_utf8!=='string'||!packed.snapshot||packed.snapshot.schema_version!==1)throw Error('缓存格式无效。');
  const saved=packed.snapshot,fetched=Date.parse(saved.fetched_at_utc);
  if(!Number.isFinite(fetched)||fetched>Date.now()+300000)throw Error('缓存获取时间无效。');
  const req=request(key,product,fetched),snapshot=normalize(packed.raw_utf8,req,saved.fetched_at_utc),digest=await hash(packed.raw_utf8);
  const keys=['date','start_utc','end_utc','rain_mm','temperature_mean_c','humidity_mean_pct','hours_present','hours_expected','status'];
  const derivedNumbers=new Set(['rain_mm','temperature_mean_c','humidity_mean_pct']);
  const sameRows=Array.isArray(saved.rows)&&saved.rows.length===snapshot.rows.length&&saved.rows.every((row,i)=>keys.every(key=>{
   const a=row[key]??null,b=snapshot.rows[i][key]??null;
   return derivedNumbers.has(key)&&numeric(a)&&numeric(b)?Math.abs(a-b)<=1e-4:a===b;
  }));
  const savedUrl=new URL(saved.request_url),expectedUrl=new URL(req.request_url);
  const sameUrl=savedUrl.origin===expectedUrl.origin&&savedUrl.pathname===expectedUrl.pathname&&[...savedUrl.searchParams].length===[...expectedUrl.searchParams].length&&[...expectedUrl.searchParams].every(([k,v])=>savedUrl.searchParams.get(k)===v);
  if(saved.raw_sha256!==digest.raw_sha256||saved.raw_bytes!==digest.raw_bytes||saved.product!==product||saved.location.key!==key||!sameUrl||!sameRows)throw Error('缓存摘要、位置或数据内容不符。');
  Object.assign(snapshot,digest);memory[storageKey(key,product)]={snapshot,raw_utf8:packed.raw_utf8};
 }catch(error){errors[storageKey(key,product)]='已隔离损坏缓存：'+error.message}
}
async function refreshOne(key,product){
 const req=request(key,product);
 try{
  const response=await fetch(req.request_url,{signal:AbortSignal.timeout(25000),cache:'no-store'});
  if(!response.ok)throw Error(response.status===429?'接口访问频繁，请稍后再试':`接口HTTP ${response.status}`);
  const bytes=await response.arrayBuffer();if(bytes.byteLength>4000000)throw Error('响应超过允许大小。');
  const raw=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes);
  const snapshot=normalize(raw,req,new Date().toISOString());Object.assign(snapshot,await hash(raw));
  const packed={snapshot,raw_utf8:raw};memory[storageKey(key,product)]=packed;delete errors[storageKey(key,product)];
  try{localStorage.setItem(storageKey(key,product),JSON.stringify(packed))}catch{errors[storageKey(key,product)]='本次获取成功，但浏览器无法保存缓存。当前页仍可查看。'}
 }catch(error){errors[storageKey(key,product)]=error.name==='TimeoutError'?'接口超时，保留上次有效结果':error.name==='TypeError'?'网络或跨域请求失败，保留上次有效结果':error.message}
 if(locationKey===key)renderOnline();
}
function stats(items){return `<div class="live-stats">${items.map(([value,label])=>`<div class="live-stat"><b class="number">${safe(value)}</b><small>${safe(label)}</small></div>`).join('')}</div>`}
function chart(snapshot){
 const rows=snapshot.rows,w=760,h=220,padX=35,padY=25,max=Math.max(5,...rows.filter(r=>r.rain_mm!==null).map(r=>r.rain_mm)),x=i=>padX+i/Math.max(1,rows.length-1)*(w-2*padX),y=v=>h-padY-v/max*(h-2*padY);
 let body=`<path d="M${padX} ${padY}V${h-padY}H${w-padX}" fill="none" stroke="#cbd9d1"/>`;
 [0,.5,1].forEach(k=>{const yy=y(k*max);body+=`<path d="M${padX} ${yy}H${w-padX}" stroke="#edf1ec"/><text x="${padX-7}" y="${yy+4}" text-anchor="end" font-size="11" fill="#62777d">${Math.round(k*max)}</text>`});
 if(snapshot.product==='forecast')rows.forEach((r,i)=>{if(r.rain_mm!==null){const xx=padX+(i+.5)/rows.length*(w-2*padX),width=(w-2*padX)/rows.length*.5;body+=`<rect x="${xx-width/2}" y="${y(r.rain_mm)}" width="${width}" height="${Math.max(1,h-padY-y(r.rain_mm))}" rx="5" fill="#2c8b77"><title>${safe(r.date)} · ${r.rain_mm} mm · ${r.hours_present}/24小时</title></rect><text x="${xx}" y="${y(r.rain_mm)-8}" text-anchor="middle" fill="#13786a" font-size="13">${r.rain_mm.toFixed(1)}</text><text x="${xx}" y="${h-4}" text-anchor="middle" font-size="11" fill="#62777d">${r.date.slice(5)}</text>`}else body+=`<text x="${padX+(i+.5)/rows.length*(w-2*padX)}" y="${h/2}" text-anchor="middle" fill="#a65f26" font-size="11">缺测</text>`});
 else{let pen=false,d='';rows.forEach((r,i)=>{if(r.rain_mm===null){pen=false;return}d+=(pen?'L':'M')+x(i)+' '+y(r.rain_mm);pen=true});body+=`<path d="${d}" fill="none" stroke="#288d7c" stroke-width="2.2"/><text x="${padX}" y="${h-4}" fill="#62777d" font-size="11">${rows[0]?.date||''}</text><text x="${w-padX}" y="${h-4}" text-anchor="end" fill="#62777d" font-size="11">${rows.at(-1)?.date||''}</text>`}
 return `<div class="live-chart"><svg role="img" aria-label="${snapshot.product==='forecast'?'未来完整窗口预报':'历史再分析背景'}降水曲线，单位毫米" viewBox="0 0 ${w} ${h}">${body}</svg></div>`;
}
function provenance(snapshot){return `<details><summary>来源与原始记录</summary><div class="live-meta">获取时刻（北京）：${safe(localTime(snapshot.fetched_at_utc))}<br>模型／来源：${safe(snapshot.source.model)} · UTC日窗口<br>请求位置：${snapshot.location.latitude}, ${snapshot.location.longitude}<br>返回格点：${safe(snapshot.grid.latitude)}, ${safe(snapshot.grid.longitude)}<br><a href="${safe(snapshot.request_url)}" target="_blank" rel="noopener noreferrer">打开原始接口 ↗</a><br>${safe(snapshot.source.licence)}<br>原始响应SHA-256：<code>${safe(snapshot.raw_sha256)}</code></div></details>`}
function onlineCard(product){
 const key=storageKey(locationKey,product),packed=memory[key],snapshot=packed?.snapshot,title={forecast:'未来7个完整窗口',archive:'本年度天气背景',station:'最新站点参考覆盖'}[product];
 let html=`<div class="eyebrow">${product==='forecast'?'FORECAST':product==='archive'?'ERA5 · CONTEXT':'SSOD · REFERENCE'}</div><h2>${title} ${snapshot?badge(snapshot):''}</h2>`;
 if(errors[key])html+=`<div class="live-note warning" role="status">${safe(errors[key])}${snapshot?'。下方保留缓存，不视为刚刚更新。':''}</div>`;
 if(!snapshot)return html+'<div class="live-empty">尚未保存在线数据。点击“获取最新数据”连接公开接口。历史实验和完整度报告可离线查看。</div>';
 const c=snapshot.coverage;
 html+=stats([[`${c.complete_day_count} / ${c.expected_day_count}`,'完整降水日'],[c.latest_available_date?.slice(5)||'—','最后有效降水日'],[c.expected_day_count-c.complete_day_count,'未满足完整条件的日数']]);
 if(product==='forecast')html+='<p class="fine">UTC 00–24小时，对应北京08:00至次日08:00。从明日窗口开始，降水按(start,end]聚合24个小时。这里展示数值预报，不套用历史实验概率。</p>'+chart(snapshot);
 else if(product==='archive')html+='<div class="live-note">ERA5是再分析天气背景，不是新增站点实测。用于补充天气背景覆盖；不能补入本项目的SSOD标签或计算新增避损收益。为避开数据延迟，截止日保留7天缓冲。</div>'+chart(snapshot);
 else html+=`<div class="live-note">末次报告日期：${safe(c.last_reported_date||'—')}。只有完整测量码与有效降水总量才计入完整参考，缺测不按无雨处理。在线结果另存，冻结的636日主实验和85日新增检查保持原身份。</div>`;
 html+=provenance(snapshot)+`<div class="live-downloads"><button type="button" class="button" data-live-download="${product}">下载数据与原始响应</button></div>`;
 return html;
}
function renderOnline(){products.forEach(p=>el('live-'+p).innerHTML=onlineCard(p));const found=products.filter(p=>memory[storageKey(locationKey,p)]).length;el('live-status').textContent=busy?'正在分别核查三个公开来源；其他页面仍可使用。':`${boot.locations[locationKey].name} · 已保存${found}类在线数据。只在点击按钮时联网，缓存时间会持续显示。`;}
function renderCalendar(){
 const report=boot.completeness,year=el('coverage-year').value,all=report.days.filter(r=>r.date.startsWith(year)),months=[...new Set(all.map(r=>r.month))];
 el('coverage-calendar').innerHTML=months.map(month=>{const days=all.filter(r=>r.month===month),offset=(new Date(month+'-01T00:00:00Z').getUTCDay()+6)%7;return `<div class="calendar-month"><h3>${month.slice(5)}月<span>${days.filter(r=>r.status==='paired').length}/${days.length}日配对</span></h3><div class="calendar-days">${'<span class="calendar-day empty"></span>'.repeat(offset)}${days.map(r=>`<button type="button" class="calendar-day ${r.status}" data-coverage-date="${r.date}" title="${r.date} · ${safe(r.label)}" aria-label="${r.date}，${safe(r.label)}">${Number(r.date.slice(8))}</button>`).join('')}</div></div>`}).join('');
 el('coverage-detail').textContent='点选日期查看该日状态。灰色与空框都表示缺口，不表示降水为零。';
}
function renderCompleteness(){
 const report=boot.completeness,s=report.summary;
 el('coverage-summary').innerHTML=stats([[`${s.paired_days} / ${s.configured_days}`,'主实验完整配对日'],[s.missing_reference_days,'缺少完整参考日'],[s.missing_forecast_days,'缺少配对预报日']]);
 el('coverage-fields').innerHTML=`<table><thead><tr><th>字段</th><th>可用日</th><th>覆盖率</th><th>解释</th></tr></thead><tbody>${report.fields.map(f=>`<tr><td>${safe(f.label)}</td><td>${f.available} / ${s.paired_days}</td><td>${(f.coverage*100).toFixed(1)}%</td><td>${safe(f.note)}</td></tr>`).join('')}</tbody></table>`;
 el('coverage-gaps').innerHTML=`<table><thead><tr><th>连续缺口</th><th>日数</th><th>原因</th></tr></thead><tbody>${report.gaps.slice(0,10).map(g=>`<tr><td>${g.start_date} — ${g.end_date}</td><td>${g.days}</td><td>${safe(g.label)}</td></tr>`).join('')}</tbody></table>`;
 const t=report.temporal;
 el('coverage-temporal').innerHTML=`<p class="fine">2026年1—9月独立检查仍为${t.counts.paired_windows} / ${t.counts.configured_days}日配对、${t.counts.event_count}个参考事件；4—9月没有完整参考。在线再分析背景不会改变该验证结果。</p>`;
 renderCalendar();
}
async function restore(){await Promise.all(products.map(p=>loadStored(locationKey,p)));renderOnline()}
el('live-location').addEventListener('change',async e=>{locationKey=e.target.value;renderOnline();await restore()});
el('live-refresh').addEventListener('click',async()=>{if(busy)return;busy=true;el('live-refresh').disabled=true;el('live-location').disabled=true;renderOnline();try{await Promise.allSettled(products.map(p=>refreshOne(locationKey,p)))}finally{busy=false;el('live-refresh').disabled=false;el('live-location').disabled=false;renderOnline()}});
el('coverage-year').addEventListener('change',renderCalendar);
document.addEventListener('click',e=>{
 const day=e.target.closest('[data-coverage-date]');if(day){const r=boot.completeness.days.find(x=>x.date===day.dataset.coverageDate);el('coverage-detail').textContent=`${r.date} · ${r.label}${r.status==='missing_forecast'?'：参考完整，但预报没有满足配对条件。':r.status==='incomplete_reference'?'：存在报告，但降水或测量码不完整。':r.status==='no_reference_record'?'：该配置日没有站点参考报告。':'：已纳入冻结主表。'}`}
 const button=e.target.closest('[data-live-download]');if(button){const packed=memory[storageKey(locationKey,button.dataset.liveDownload)];if(packed)downloadBytes(new TextEncoder().encode(JSON.stringify(packed,null,2)),`meiyu_${locationKey}_${button.dataset.liveDownload}.json`,'application/json')}
 if(e.target.closest('#coverage-download'))downloadBytes(new TextEncoder().encode(JSON.stringify(boot.completeness,null,2)),'meiyu_completeness.json','application/json');
});
renderCompleteness();restore();setInterval(()=>{if(!busy&&!el('view-live').hidden)renderOnline()},60000);
Object.defineProperty(window,'meiyuLive',{value:{request,normalize,parseCSV,refreshOne,getState:()=>({locationKey,busy,snapshots:Object.fromEntries(products.map(p=>[p,memory[storageKey(locationKey,p)]?.snapshot??null])),errors:{...errors}}),completeness:boot.completeness},writable:false});
})();
