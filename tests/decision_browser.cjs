'use strict';
const fs=require('node:fs'),path=require('node:path');
const {launchBrowser}=require('./browser_support.cjs');
const OUT=path.resolve(__dirname,'../../browser_validation');fs.mkdirSync(OUT,{recursive:true});
const checks=[],errors=[],requests=[];
function check(name,ok,evidence){checks.push({name,passed:!!ok,evidence});if(!ok)throw Error(name+'失败');}
async function main(){
  const {browser,launch}=await launchBrowser(),page=await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:1});
  page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>requests.push(r.url()));
  try{
    await page.goto('http://127.0.0.1:8532/',{waitUntil:'load'});
    await page.waitForFunction(()=>!!window.MEIYU_DECISION_APP&&!MEIYU_DECISION_APP.state.busy,{timeout:50000});
    const initial=await page.evaluate(()=>({weather:MEIYU_DECISION_APP.state.weather.hangzhou,gate:MEIYU_DECISION_APP.eligibility(),title:document.querySelector('#result-title').textContent}));
    check('打开自动请求',requests.some(u=>u.includes('/api/decision-weather')),requests);
    check('未确认不出结论',initial.title.includes('确认')||initial.title.includes('暂不计算'),initial.title);
    await page.screenshot({path:path.join(OUT,'desktop_initial.png'),fullPage:true});
    await page.locator('#mode-demo').click();await page.locator('#assumptions').check();
    check('示例搬货',await page.locator('#result-title').innerText()==='按当前设定，建议搬货',await page.locator('#result-card').innerText());
    check('正确预计成本',await page.locator('#expected-without').innerText()==='¥ 600.00'&&await page.locator('#expected-move').innerText()==='¥ 140.00',await page.locator('#result-card').innerText());
    await page.screenshot({path:path.join(OUT,'desktop_move.png'),fullPage:true});
    await page.locator('#move-cost').fill('600');
    check('修改金额切换不搬',(await page.locator('#result-title').innerText()).includes('暂不搬'),await page.locator('#result-card').innerText());
    await page.screenshot({path:path.join(OUT,'desktop_keep.png'),fullPage:true});
    await page.locator('#move-cost').fill('540');check('同价不强推',(await page.locator('#result-title').innerText()).includes('相同'),await page.locator('#result-title').innerText());
    await page.locator('#move-cost').fill('');check('空金额不当零',!(await page.locator('#input-error').isHidden())&&await page.locator('#download-record').isDisabled(),await page.locator('#input-error').innerText());
    await page.locator('#move-cost').fill('80');
    const downloadPromise=page.waitForEvent('download');await page.locator('#download-record').click();const download=await downloadPromise;await download.saveAs(path.join(OUT,'demo_record.json'));
    const record=JSON.parse(fs.readFileSync(path.join(OUT,'demo_record.json'),'utf8'));check('账单不冒充真实天气',record.mode==='demo'&&record.probability_kind==='hypothetical_demo'&&record.fetched_at_utc===null,record);
    await page.locator('#mode-live').click();check('切回实况重新确认',!await page.locator('#assumptions').isChecked(),await page.locator('#result-title').innerText());
    await page.waitForFunction(()=>!MEIYU_DECISION_APP.state.busy,{timeout:50000});
    await page.evaluate(()=>{const s=MEIYU_DECISION_APP.state;s.weather[s.location].snapshot.fetched_at_utc='2020-01-01T00:00:00Z';document.getElementById('assumptions').checked=true;MEIYU_DECISION_APP.render();});
    check('过期暂停结论',(await page.locator('#result-title').innerText()).includes('暂不计算')&&await page.locator('#download-record').isDisabled(),await page.locator('#result-card').innerText());
    await page.locator('#mode-demo').click();await page.locator('#assumptions').check();
    await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(OUT,'mobile_move.png'),fullPage:true});
    const mobile=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,viewport:innerWidth}));check('手机无横向溢出',mobile.scroll<=mobile.viewport,mobile);
    check('页面无错误',errors.length===0,errors);
    const report={status:'PASS',checks,errors,requests,browser:launch.metadata,initial,finished_at_utc:new Date().toISOString()};fs.writeFileSync(path.join(OUT,'report.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify({status:report.status,checks:checks.length,out:OUT}));
  }catch(error){fs.writeFileSync(path.join(OUT,'report.json'),JSON.stringify({status:'FAIL',checks,errors,requests,error:String(error.stack)},null,2));throw error;}finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
