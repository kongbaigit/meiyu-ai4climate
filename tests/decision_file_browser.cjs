'use strict';
const fs=require('node:fs'),path=require('node:path'),{pathToFileURL}=require('node:url');
const {launchBrowser}=require('./browser_support.cjs');
const ROOT=path.resolve(__dirname,'..'),OUT=path.resolve(ROOT,'../file_validation');fs.mkdirSync(OUT,{recursive:true});
async function main(){
 const {browser}=await launchBrowser(),page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const folder=path.join(ROOT,'runtime/decision_weather/hangzhou'),index=JSON.parse(fs.readFileSync(path.join(folder,'current.json'),'utf8'));
 const raw=fs.readFileSync(path.join(folder,index.raw_file),'utf8'),expected=JSON.parse(fs.readFileSync(path.join(folder,index.snapshot_file),'utf8'));
 let responseRaw=raw,requests=0;
 await page.route('https://ensemble-api.open-meteo.com/**',route=>{requests++;return route.fulfill({status:200,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:responseRaw});});
 try{
  await page.goto(pathToFileURL(path.join(ROOT,'index.html')).href);await page.waitForFunction(()=>window.MEIYU_DECISION_APP&&!MEIYU_DECISION_APP.state.busy&&MEIYU_DECISION_APP.state.weather.hangzhou?.snapshot,{timeout:15000});
  const state=await page.evaluate(()=>({gate:MEIYU_DECISION_APP.eligibility(),mode:document.getElementById('service-mode').textContent}));
  if(!state.gate.ok||!state.mode.includes('打开'))throw Error('file模式自动更新或模式说明失败');
  const parsed=await page.evaluate(async({raw,expected})=>{return MEIYU_DECISION_APP.parseRaw(raw,'hangzhou',expected.fetched_at_utc,expected.windows.map(w=>({start_utc:w.start_utc,end_utc:w.end_utc})),expected.request_url);},{raw,expected});
  if(JSON.stringify(parsed.windows)!==JSON.stringify(expected.windows)) {
    for(let i=0;i<7;i++)for(const field of Object.keys(expected.windows[i]))if(parsed.windows[i][field]!==expected.windows[i][field])throw Error('前后端解析不一致：'+i+'/'+field);
  }
  const before=await page.evaluate(()=>MEIYU_DECISION_APP.state.weather.hangzhou.snapshot.raw_sha256);
  const partial=JSON.parse(raw);delete partial.hourly.precipitation_member01;responseRaw=JSON.stringify(partial);
  await page.evaluate(()=>MEIYU_DECISION_APP.refresh(true));
  const kept=await page.evaluate(()=>({sha:MEIYU_DECISION_APP.state.weather.hangzhou.snapshot.raw_sha256,error:MEIYU_DECISION_APP.state.weather.hangzhou.error}));
  if(kept.sha!==before||!kept.error?.includes('保留'))throw Error('部分响应替换了完整缓存');
  const partialResult=await page.evaluate(async raw=>{const a=MEIYU_DECISION_APP;const w=a.windowSpecs();const s=await a.parseRaw(raw,'hangzhou',new Date().toISOString(),w,a.requestURL('hangzhou',w));a.state.weather.hangzhou={snapshot:s,status:'partial'};document.getElementById('assumptions').checked=true;a.render();return {p:s.windows[0].probability,gate:a.eligibility(),result:a.state.result};},responseRaw);
  if(partialResult.p!==null||partialResult.gate.ok||partialResult.result!==null)throw Error('缺成员仍输出结论');
  if(errors.length)throw Error('页面错误：'+errors.join(','));
  const report={status:'PASS',scope:'file模式自动请求与真实原始响应重放，不把重放称作本轮真实网络获取',requests,python_js_windows_equal:true,full_cache_preserved:true,missing_member_blocks:true,errors,checked_at_utc:new Date().toISOString()};fs.writeFileSync(path.join(OUT,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
