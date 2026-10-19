const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto,createHash} = require('node:crypto');
const source = fs.readFileSync(path.join(__dirname,'../templates/downloads.js'),'utf8');

function harness(mode){
  let handler, calls=0, saved=0;
  const status={textContent:''};
  const data=Buffer.from('original public archive');
  const entry={name:'test.zip',type:'application/zip',bytes:data.length,sha256:createHash('sha256').update(data).digest('hex'),parts:['a','b']};
  const button={disabled:false,dataset:{download:'source'},parentElement:{querySelector:()=>status},addEventListener:(_,fn)=>handler=fn};
  const document={querySelectorAll:()=>[button],body:{appendChild:()=>{}},createElement:()=>({click:()=>saved++,remove:()=>{}})};
  const fetch=async url=>{calls++;if(url==='downloads.json')return {ok:true,json:async()=>({source:entry})};if(mode==='network')return {ok:false};let part=url==='a'?data.subarray(0,5):data.subarray(5);if(mode==='corrupt'&&url==='b')part=Buffer.from(part).fill(88);return {ok:true,arrayBuffer:async()=>Uint8Array.from(part).buffer};};
  vm.runInNewContext(source,{document,fetch,Blob,crypto:webcrypto,URL:{createObjectURL:()=> 'blob:test',revokeObjectURL:()=>{}},setTimeout:()=>{}});
  return {run:()=>handler(),status,button,get calls(){return calls},get saved(){return saved}};
}
test('only user click starts download; intact archive reaches save',async()=>{const h=harness('ok');assert.equal(h.calls,0);await h.run();assert.equal(h.saved,1);assert.match(h.status.textContent,/校验通过/);assert.equal(h.button.disabled,false)});
test('network failure does not save and permits retry',async()=>{const h=harness('network');await h.run();assert.equal(h.saved,0);assert.match(h.status.textContent,/中断/);assert.equal(h.button.disabled,false)});
test('same-length corruption is rejected before save',async()=>{const h=harness('corrupt');await h.run();assert.equal(h.saved,0);assert.match(h.status.textContent,/校验失败/);assert.equal(h.button.disabled,false)});
