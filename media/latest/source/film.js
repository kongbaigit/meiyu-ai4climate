(() => {
'use strict';
const I=FILM_INPUT,D=I.evidence,S=I.timeline.scenes,V=I.timeline.visual_scenes,C=I.timeline.music_sync,W=1920,H=1080,T=I.timeline.duration,B=60/140;
const actualBeat=C.beat_seconds,beatMap=I.timeline.visual_beat_map;
function visualTime(t){
  const b=Math.max(0,Math.min(112,t/actualBeat));let k=1;
  while(k<beatMap.length-1&&b>beatMap[k][1])k++;
  const lo=beatMap[k-1],hi=beatMap[k],p=(b-lo[1])/(hi[1]-lo[1]);
  return (lo[0]+(hi[0]-lo[0])*p)*B;
}
const canvas=document.getElementById('film'),ctx=canvas.getContext('2d',{alpha:false});
const legacy=createMeiyuLegacy3D(I.legacy_evidence,I.legacy_timeline);
const P={paper:'#f3f2e9',white:'#fffef8',ink:'#173e36',green:'#286c60',mint:'#c8e3b3',dim:'#687c6c',line:'#d6dfcf',dark:'#102e2a',cream:'#f0efd7',warm:'#e8be78',red:'#d98c66'};
const FACE='"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif',MONO='Consolas,monospace';
const clamp=(x,a=0,b=1)=>Math.max(a,Math.min(b,x)),ease=x=>{x=clamp(x);return x*x*(3-2*x);},phase=(a,b,t)=>ease((t-a)/(b-a));
const seed=(i,k=0)=>{const x=Math.sin(i*128.137+k*321.7+7.3)*43758.515;return x-Math.floor(x);};
const dark=i=>[0,3,5,7,9].includes(i),money=n=>n.toLocaleString('en-US',{maximumFractionDigits:0});
const nominal=[6,7,7,10,9,4,10,7,7,5];
const RAIN_MAX=Math.max(.1,...D.weather.matrix.flat().filter(Number.isFinite));
let bounds=[],state={},playing=false,now=0,started=0,raf=0,frameTime=0;
const M=Object.fromEntries(S.map(s=>[s.id,{enter:0,a:0,b:0,c:0}]));
Object.assign(M.schema,{table:0});Object.assign(M.model,{curve:0});
Object.assign(M.ensemble,{heat:0,aggregate:0});Object.assign(M.integrity,{hole:0,stop:0});
Object.assign(M.decision,{compact:0,without:0,move:0,benefit:0,field0:0,field1:0,field2:0});Object.assign(M.sensitivity,{cost:80});
const master=gsap.timeline({paused:true,defaults:{overwrite:false}});
for(const s of V){
  master.fromTo(M[s.id],{enter:0},{enter:1,duration:.32*B,ease:'power2.out',immediateRender:false},s.start);
  for(const [name,offset] of [['a',0],['b',s.id==='opening'?4:s.id==='closing'?4:1],['c',s.id==='opening'?8:2]])
    master.fromTo(M[s.id],{[name]:0},{[name]:1,duration:.65*B,ease:'power3.out',immediateRender:false},s.start+offset*B);
}
function tween(id,key,startBeat,durationBeats){const land=['without','move','benefit'].includes(key);master.fromTo(M[id],{[key]:0},{[key]:1,duration:durationBeats*B,ease:'power3.out',immediateRender:false},(startBeat-(land?durationBeats:0))*B);}
tween('schema','table',36,1);tween('model','curve',56,1);
tween('ensemble','heat',76,4);tween('ensemble','aggregate',84,2);
tween('integrity','hole',94,.4);tween('integrity','stop',96,.4);
tween('decision','field0',100,.5);tween('decision','field1',101,.5);tween('decision','field2',102,.5);
tween('decision','compact',106,1);tween('decision','without',110,.4);tween('decision','move',112,.4);tween('decision','benefit',114,.4);
master.fromTo(M.sensitivity,{cost:80},{cost:540,duration:4*B,ease:'power2.inOut',immediateRender:false},126*B);
master.fromTo(M.sensitivity,{cost:540},{cost:600,duration:2*B,ease:'power2.inOut',immediateRender:false},132*B);
master.to({},{duration:.01},71.99);gsap.ticker.sleep();
/*__DRAWING_HELPERS__*/

function group(alpha,draw){ctx.save();ctx.globalAlpha*=clamp(alpha);draw();ctx.restore();}
function path(points,color,width=3,alpha=1){ctx.save();ctx.globalAlpha*=alpha;ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.strokeStyle=color;ctx.lineWidth=width;ctx.lineJoin='round';ctx.stroke();ctx.restore();}
function title(i,kicker,text){const d=dark(i),m=M[S[i].id];txt(kicker,98,190,22,d?P.mint:P.green,500,'left',1,MONO);txt(text,94,289+(1-m.enter)*(i===4?12:35),70,d?P.cream:P.ink,650,'left',m.enter);}
function badge(value,x,y,i){return pill(value,x,y,dark(i)?'#294b3d':'#e2ead8',dark(i)?P.mint:P.green,22);}
function foot(value,i){txt(value,100,942,25,dark(i)?'#a7c2a6':P.dim,450);}
function common(t,i){
  const d=dark(i),ink=d?P.cream:P.ink;
  logo(113,60,27,d?P.mint:P.green);txt('梅雨有数',146,73,30,ink,650);
  txt('数据 · 算法 · 搬货决策',1808,72,21,d?'#a8c3aa':P.dim,500,'right');
  line(98,112,1822,112,d?'#36534a':P.line);
  const gap=10,w=(1720-gap*(S.length-1))/S.length;
  S.forEach((s,j)=>{const x=100+j*(w+gap),p=clamp((t-s.start)/(s.end-s.start));line(x,1004,x+w,1004,d?'#335446':P.line,3);if(p)line(x,1004,x+w*p,1004,d?P.mint:P.green,3);});
  txt(String(i+1).padStart(2,'0')+' / '+S[i].label,100,1047,20,d?'#a9c5a9':P.dim,500);
  txt(Math.round(T)+'秒 / 原速配乐 / 无配音',1820,1047,19,d?'#88aa92':P.dim,450,'right',1,MONO);
}
function opening(u){
  const m=M.opening;
  group(.95,()=>ctx.drawImage(legacy.render(0,2+u*1.9),0,0,W,H));
  txt('雨前搬货成本计算',103,213,26,P.mint,500);
  txt('雨要来了。',94,369+(1-m.a)*35,102,P.cream,650,'left',m.a);
  txt('这批货，',94,516+(1-m.b)*40,102,P.cream,650,'left',m.b);
  txt('搬不搬？',90,713+(1-m.c)*45,164,P.cream,650,'left',m.c);
  const a=phase(10,11,frameTime/B);group(a,()=>{badge('天气',1125,270,0);badge('成本',1395,270,0);line(1222,255,1378,255,'#52785c',2);});
  txt('先把天气和成本放在一起。',103,869,34,'#bfd5b3',450,'left',m.c);
}
function sources(u){
  ctx.drawImage(legacy.render(1,1+u*1.7),0,0,W,H);
  txt('01 / SOURCE TO SAMPLE',100,190,22,P.green,500,'left',1,MONO);
  txt('公开数据，',96,301,76,P.ink,650);txt('留下每次配对。',96,405,76,P.ink,650);
  const rows=[['公开预报','forecast_rain_mm'],['站点参考','observed_rain_mm'],['同一24小时窗口','window_start_utc']];
  rows.forEach(([label,key],j)=>{const a=phase(16+4*j,17+4*j,frameTime/B);group(a,()=>{rr(100,470+j*117,627,99,12,P.white,P.line);txt(label,127,513+j*117,31,P.green,550);txt(key,127,548+j*117,22,P.dim,450,'left',1,MONO);});});
  foot('数据沿来源路径汇聚；三维砖块对应636个历史完整配对日。',1);
}
function schema(u){
  const m=M.schema,h=D.history;
  const change=clamp(frameTime/B-36);
  title(2,'02 / DATA STRUCTURE','数据先对齐。');
  txt(h.sample_count,1717,280,106,P.green,550,'right');txt('个完整配对日',1720,330,27,P.dim,450,'right');
  group(1-phase(0,.42,change),()=>{
    for(const [j,label,small] of [[0,'公开预报','forecast_rain_mm'],[1,'站点参考','observed_rain_mm']]){
      const x=100+j*920;rr(x,418,800,233,18,P.white,P.line);txt(label,x+44,492,43,P.ink,550);txt(small,x+44,558,28,P.dim,450,'left',1,MONO);txt('24小时窗口',x+44,611,29,P.green,500);
    }
    arrow(913,534,1004,534,P.green,3);txt('UTC 00:00 → 次日00:00',960,756,35,P.green,500,'center');
  });
  group(phase(.52,1,change),()=>{
    txt('一行 = 同一24小时窗口的预报与参考配对',101,362,31,P.dim,450);
    rr(100,403,1720,469,17,P.white,P.line);
    const xs=[130,575,942,1301],labels=['UTC日窗','预报雨量 / mm','参考雨量 / mm','质量状态'],fields=['window_start_utc','forecast_rain_mm','observed_rain_mm','quality_status'];
    rr(101,404,1718,100,16,'#e4ecdc');
    xs.forEach((x,j)=>{txt(labels[j],x,449,29,P.ink,550);txt(fields[j],x,483,21,P.dim,450,'left',1,MONO);});
    h.rows.slice(0,5).forEach((r,j)=>{
      const y=555+j*69,p=phase(40+j-.45,40+j,frameTime/B);
      if(j===1)rr(112,y-39,1696,61,8,'#eef2e6');
      group(p,()=>{txt(r.date||r.window_start_utc.slice(0,10),130,y,32,P.ink,500,'left',1,MONO);txt(Number(r.forecast_rain_mm).toFixed(1),575,y,35,P.green,550,'left',1,MONO);txt(Number(r.observed_rain_mm).toFixed(1),942,y,35,P.ink,500,'left',1,MONO);dot(1310,y-10,6,P.green);txt(r.quality_status,1331,y,27,P.green,500,'left',1,MONO);});
    });
    if(frameTime/B>=38){const cols=[[120,430],[563,350],[930,340],[1289,500]],j=Math.min(3,Math.floor((frameTime/B-38)/2)),[x,w]=cols[j];rr(x,577,w,61,8,null,P.green,2.5);}
  });
  foot('历史样本 · 来源、日界和排除原因均保留，可回到原始文件核对。',2);
}
function model(u){
  const m=M.model,h=D.history,hm=h.model,e=h.example;
  const change=clamp(frameTime/B-56);
  title(3,'03 / HISTORICAL MODEL','历史模型，怎样得到一个概率。');badge('历史离线实验',1490,190,3);
  group(1-phase(0,.42,change),()=>{
    ctx.drawImage(legacy.render(5,Math.min(14,u*3)),0,0,W,H);
    const cols=[['训练','train',P.mint],['验证','validation',P.warm],['测试','test','#b0cbd4']];
    cols.forEach(([label,key,color],j)=>{const y=395+j*148,p=phase(j*.3,.6+j*.3,u);group(p,()=>{txt(label,102,y+50,36,color,550);txt(h.split_counts[key].sample_count,285,y+61,80,P.cream,500);txt('日',489,y+60,32,'#abc3a6');line(101,y+96,655,y+96,'#375747',1);});});
    txt('按时间向后切分。',100,891,31,'#bfd4b7');
  });
  group(phase(.52,1,change),()=>{
    const nodes=[['预报雨量','x'],['log1p','ln(1+x)'],['标准化','z'],['逻辑回归','p']];
    nodes.forEach(([label,sub],j)=>{const x=100+j*297;group(phase(56+j,56.5+j,frameTime/B),()=>{rr(x,343,260,96,12,'#1b4035','#3c5d4d');txt(label,x+130,385,28,P.mint,550,'center');txt(sub,x+130,420,22,'#94b69a',450,'center',1,MONO);if(j<3)arrow(x+267,390,x+287,390,'#89ad8a',2);});});
    const gx=150,gy=810,gw=1010,gh=300;
    [0,.5,1].forEach(v=>{line(gx,gy-v*gh,gx+gw,gy-v*gh,'#315344',1);txt(v.toFixed(1),gx-23,gy-v*gh+8,21,'#9ebd9f',450,'right',1,MONO);});
    line(gx,gy,gx+gw,gy,'#789c7c',2);line(gx,gy,gx,gy-gh,'#789c7c',2);
    const points=[];const reveal=phase(60,64,frameTime/B);for(let k=0;k<=160*reveal;k++){const z=-2+7*k/160,p=1/(1+Math.exp(-(hm.coefficient*z+hm.intercept)));points.push([gx+gw*k/160,gy-gh*p]);}if(points.length>1)path(points,P.mint,5);
    const ex=clamp((e.standardized+2)/7),ey=e.probability;
    group(phase(64,64.5,frameTime/B),()=>{line(gx+gw*ex,gy,gx+gw*ex,gy-gh*ey,P.warm,2);dot(gx+gw*ex,gy-gh*ey,8,P.warm);});
    txt('标准化后的降水特征 z',gx+gw/2,865,25,'#a8c3a4',450,'center');
    rr(1313,343,507,539,18,'#1b4035','#3b5c4a');txt('真实历史样本',1350,400,30,P.mint,550);txt(e.window_start_utc.slice(0,10),1350,449,26,'#a4bea4',450,'left',1,MONO);
    txt('预报雨量 '+Number(e.forecast_rain_mm).toFixed(1)+' mm',1350,508,29,P.cream,500);
    txt('log1p → '+Number(e.log1p).toFixed(3),1350,561,25,'#a6c3a6',450,'left',1,MONO);
    txt('z → '+Number(e.standardized).toFixed(3),1350,605,25,'#a6c3a6',450,'left',1,MONO);
    txt((100*e.probability).toFixed(1)+'%',1350,741,92,P.cream,550);
    txt('参考日降水 ≥25mm 的估计',1350,796,25,P.mint,450);
    txt('仅用于该历史离线实验',1350,845,24,'#a0bca1',450);
  });
  foot('模型：logistic_rain · 训练参数冻结；当前在线天气使用另一条集合预报流程。',3);
}
function rainColor(value){const v=clamp(value/RAIN_MAX);return `rgb(${Math.round(222-178*v)},${Math.round(234-119*v)},${Math.round(207-118*v)})`;}
function matrix(x,y,w,h,{missing=false,alpha=1,columns=24}={}){
  const a=D.weather.matrix,cw=w/24,rh=h/51;
  group(alpha,()=>{a.forEach((row,r)=>row.forEach((value,c)=>{
    if(c>=columns)return;const isHole=missing&&r===13&&c===11;
    rr(x+c*cw+1,y+r*rh+1,cw-3,Math.max(2,rh-2),1,isHole?'#efc982':rainColor(value),isHole?'#e9b15c':null,2);
    if(isHole){line(x+c*cw+9,y+r*rh+2,x+(c+1)*cw-10,y+(r+1)*rh-1,P.dark,2);}
  }));});
}
function ensemble(u){
  const m=M.ensemble,w=D.weather,win=w.snapshot.windows[0],change=clamp((frameTime/B-84)/2),a=phase(.3,1,change),detail=phase(.86,1,a);
  title(4,'04 / LIVE ENSEMBLE','51个成员，逐小时展开。');
  rr(100,330,1720,58,11,'#e7edde');
  txt('预报窗口',124,367,24,P.green,550);
  txt(w.window_label,270,367,25,P.ink,500,'left',1,MONO);
  txt('北京时间',827,367,22,P.dim,450);
  txt('24小时降水 · 单位 mm',1790,367,23,P.dim,450,'right');
  group(1-phase(0,.25,change),()=>{txt('51',100,545,154,P.green,550);txt('个集合成员',105,601,33,P.ink,500);txt('含控制成员',108,648,25,P.dim);txt('× 24',100,765,92,P.ink,500);txt('小时降水',108,819,29,P.dim);});
  const x=650-550*a,y=438,wid=1155-165*a,hei=387-21*a;
  group(1-m.heat,()=>{
    const max=Math.max(.1,...w.matrix.flat());
    w.matrix.forEach((row,j)=>{const p=row.map((v,k)=>[x+k*wid/23,y+j*hei/51-(v/max)*32]);path(p,'#3d8068',1.4,.17+seed(j)*.35);});
  });
  matrix(x,y,wid,hei,{alpha:m.heat,columns:24*phase(76,80,frameTime/B)});
  if(frameTime/B>=80&&change<.25){const row=13;group(1-phase(0,.25,change),()=>{rr(x,y+row*hei/51,wid,hei/51,2,null,P.green,2);txt('member13：24小时合计 '+Number(w.totals[row]).toFixed(1)+' mm',650,897,25,P.green,550);});}
  txt('成员',x,y-24,20,P.dim,450);txt('小时 →',x+wid,y-24,20,P.dim,450,'right');
  [0,12,24,36,50].forEach(r=>txt(String(r+1).padStart(2,'0'),x-13,y+hei*(r+.7)/51,18,P.dim,450,'right',1,MONO));
  for(const c of [0,6,12,18,23])txt(String(c+1).padStart(2,'0'),x+(c+.5)*wid/24,y+hei+33,21,P.dim,450,'center',1,MONO);
  group(detail,()=>{
    rr(1210,438,610,366,18,P.white,P.line);txt('日累计 ≥25mm',1246,489,31,P.green,550);
    txt(win.event_members+' / '+win.members_expected,1242,599,91,P.ink,550);
    txt('达到阈值的成员',1248,645,27,P.dim);
    line(1245,674,1780,674,P.line,2);txt((100*win.probability).toFixed(1)+'%',1244,774,80,P.green,550);
    txt('成员占比 · 未经本地校准',1220,868,27,P.dim,450);
    txt('逐成员累计24小时，再统计命中数。',100,891,29,P.green,500);
  });
  foot(w.capture_label+' · 真实响应快照 · 不是货损概率',4);
}
function integrity(u){
  const m=M.integrity;
  title(5,'05 / COMPLETENESS','缺一个小时，也暂停建议。');badge('缺失情景演示',1470,190,5);
  matrix(100,369,1000,421,{missing:m.hole>.5});
  const y=369+421*(13.5/51),x=100+1000*(11.5/24);
  if(m.hole>.1){ctx.save();ctx.strokeStyle=P.warm;ctx.lineWidth=3;ctx.beginPath();ctx.arc(x,y,20+7*Math.sin(u*5),0,Math.PI*2);ctx.stroke();ctx.restore();line(x+24,y,1190,y,P.warm,2);}
  rr(1205,369,615,421,18,'#1e4034','#5c6d47');
  txt(m.hole>.5?'23 / 24':'24 / 24',1248,497,88,m.hole>.5?P.warm:P.mint,550);
  txt('该成员的完整小时数',1251,554,30,'#b7c9ab');
  group(m.stop,()=>{rr(1246,606,530,108,13,'#e8be78');txt('暂停当前建议',1511,676,45,P.dark,650,'center');});
  txt('不补零',102,879,45,P.warm,550);txt('完整成员与小时全部通过，才计算成员占比。',366,878,32,'#bed0b1',450);
  foot('此处主动遮掉一个数据格，演示实际完整度规则；不是当前接口发生缺失。',5);
}
function decision(u){
  const m=M.decision,c=m.compact,r=MeiyuDecision.calculate({probability:.6,move_cost:80,loss_without:1000,loss_after:100});
  title(6,'06 / EXPECTED COST','同一个情景，比较两种选择。');badge('算账示例 · p=60%为假设',1330,190,6);
  const fields=[['搬货成本 C',80],['不搬条件平均损失 L₀',1000],['搬后条件平均损失 L₁',100]];
  fields.forEach(([label,value],j)=>{
    const x=100+j*578,y=385-35*c,h=308-130*c;
    group(M.decision['field'+j],()=>{rr(x,y,546,h,17,P.white,P.line);txt(label,x+31,y+57,28,P.dim,500);
    txt('¥ '+money(value),x+29,y+174-41*c,83-20*c,P.ink,550);
    if(c<.8)group(1-c,()=>txt(j===0?'人工60元 + 耗材20元（示例）':'该等级降雨发生时的平均估计',x+32,y+253,25,P.dim));});
  });
  group(phase(107,107.5,frameTime/B),()=>{
    const values=[['不搬',r.expected_without,'0.6 × 1,000'],['搬',r.expected_move,'80 + 0.6 × 100']];
    values.forEach(([label,value,formula],j)=>{const x=100+j*870,p=j?m.move:m.without;rr(x,559,850,272,18,j?'#dce9cf':P.white,j?'#aac7a3':P.line,1.5);txt(label+' · 预计总成本',x+34,618,32,P.ink,550);txt(formula,x+36,677,29,P.dim,450,'left',1,MONO);group(p,()=>txt('¥ '+money(Math.round(value*p)),x+812,783+12*(1-p),96+8*(1-p),j?P.green:P.ink,550,'right'));});
    group(m.benefit,()=>{txt('搬货的预计总成本少460元。',100,897,40,P.green,600);});
  });
  group(1-c,()=>{txt('确认三项金额，搬后剩余损失也计入。',100,827,36,P.green,500);});
  foot('60%与金额均为演示假设；条件平均损失考虑可能不受损，预计差额不是已实现收益。',6);
}
function sensitivity(){
  const cost=Math.round(M.sensitivity.cost),r=MeiyuDecision.calculate({probability:.6,move_cost:cost,loss_without:1000,loss_after:100});
  title(7,'07 / CHANGE THE COST','费用改变，选择也会改变。');badge('同一算账示例 · p=60%',1390,190,7);
  const gx=152,gy=811,gw=938,gh=385,x=v=>gx+v/700*gw,y=v=>gy-v/800*gh;
  [0,200,400,600,800].forEach(v=>{line(gx,y(v),gx+gw,y(v),'#345343',1);txt(v,gx-17,y(v)+8,21,'#a6c3a3',450,'right',1,MONO);});
  [0,200,400,600].forEach(v=>txt(v,x(v),gy+35,22,'#a6c3a3',450,'center',1,MONO));
  line(gx,gy,gx+gw,gy,'#6f9478',2);line(gx,gy,gx,gy-gh,'#6f9478',2);
  line(gx,y(600),gx+gw,y(600),'#b9cfc2',3);line(gx,y(60),gx+gw,y(760),P.mint,4);
  txt('不搬',gx+gw-8,y(600)-18,27,'#bfd3c2',500,'right');txt('搬',gx+gw-8,y(760)-18,27,P.mint,500,'right');
  line(x(cost),gy,x(cost),y(cost+60),P.warm,2);dot(x(cost),y(cost+60),9,P.warm);
  txt('搬货成本 C / 元',gx+gw/2,899,28,'#bdd1b6',450,'center');
  pill('同价点 540元',572,385,'#304d38',P.warm,25);
  dot(x(540),y(600),6,P.warm);line(x(540),y(600)+12,x(540),gy,'#7c8d5f',1.5,.6);
  const cards=[['不搬',r.expected_without,r.state==='keep'],['搬',r.expected_move,r.state==='move']];
  cards.forEach(([label,value,win],j)=>{win=win&&!(r.state==='keep'&&frameTime<134*B);const xx=1225,yy=355+j*229;rr(xx,yy,595,207,16,win?'#2e503a':'#1c3e34',win?P.mint:'#3b5b48',win?2:1);txt(label+' · 预计总成本',xx+29,yy+52,30,win?P.mint:'#a9c5aa',500);txt('¥ '+money(value),xx+31,yy+151,94,P.cream,550);});
  txt('搬货费 ¥'+money(cost),1227,871,37,P.warm,600);
  txt(r.state==='tie'?'两种选择同价':r.state==='keep'?(frameTime<134*B?'正在调整费用':'按当前设定，暂不搬'):'按当前设定，建议搬货',1227,924,31,P.mint,550);
}
function receipt(u){
  const m=M.receipt;title(8,'08 / TRACEABLE RECORD','每次选择，都留下计算依据。');
  const fields=[['mode','demo'],['probability_kind','hypothetical_demo'],['calculation.move_cost','600'],['calculation.expected_without','600'],['calculation.expected_move','660'],['calculation.state','keep']];
  rr(100,355,1022,516,18,P.white,P.line);txt('梅雨有数_搬货账单.json',135,411,29,P.green,550,'left',1,MONO);line(133,439,1088,439,P.line);
  fields.forEach(([key,value],j)=>{const p=phase(140+j*2,141+j*2,frameTime/B);group(p,()=>{txt(key,141,499+j*62,27,P.dim,450,'left',1,MONO);txt(value,1063,499+j*62,31,P.ink,550,'right',1,MONO);});});
  group(m.b,()=>{const a=1-m.b;rr(1245,414+a*40,575,376,18,'#e1ebd7');logo(1304,474+a*40,30,P.green);txt('本次算账示例',1351,488+a*40,36,P.ink,550);txt('假设、模式和结果',1280,601+a*40,36,P.green,500);txt('一起保存在本机。',1280,663+a*40,36,P.green,500);});
  foot('演示账单保留demo身份；当前天气账单另含获取时间、窗口和原始响应摘要。',8);
}
function closing(u){
  const m=M.closing;group(m.a,()=>{logo(963,309,77,P.mint);txt('梅雨有数',960,545,142,P.cream,650,'center');});
  group(m.b,()=>{txt('算清成本，再决定搬不搬。',960,681,51,'#c7dcb9',500,'center');line(557,754,1363,754,'#45684e',2);txt('kongbaigit.github.io/meiyu-ai4climate',960,846,30,P.mint,450,'center',1,MONO);});
  group(phase(160,162,frameTime/B),()=>{
    txt('Young Visionaries',960,895,22,'#c0d2b4',450,'center');
    txt('Music by Eric Matyas',960,930,21,'#c0d2b4',450,'center');
    txt('www.soundimage.org',960,963,20,'#9bb89f',450,'center',1,MONO);
  });
}
const draw=[opening,sources,schema,model,ensemble,integrity,decision,sensitivity,receipt,closing];
const indexAt=t=>{const i=S.findIndex(s=>t<s.end);return i<0?S.length-1:i;};
function transition(t,i){
  if(!i)return;const age=(t-S[i].start)/actualBeat;
  if(age<0||age>.5)return;
  const fills=[P.green,P.mint,P.paper,P.ink];
  for(let k=0;k<4;k++){
    const p=ease((age-k*.035)/.34),height=H*(1-p);
    if(height>0){ctx.fillStyle=fills[k];ctx.fillRect(k*W/4,k%2?H-height:0,W/4+1,height);}
  }
}
function renderFrame(t){
  t=clamp(Number(t)||0,0,T-.000001);frameTime=visualTime(t);master.totalTime(frameTime,false);bounds=[];
  const i=indexAt(t),s=S[i],u=(t-s.start)*nominal[i]/(s.end-s.start),d=dark(i);
  ctx.fillStyle=d?P.dark:P.paper;ctx.fillRect(0,0,W,H);
  if(d){const g=ctx.createRadialGradient(1510,440,15,1400,500,1000);g.addColorStop(0,'#376a4928');g.addColorStop(1,'#102e2a00');ctx.fillStyle=g;ctx.fillRect(0,112,W,880);}
  group(Math.max(.08,M[s.id].enter),()=>draw[i](u));common(t,i);transition(t,i);
  const cost=i>=7?Math.round(M.sensitivity.cost):80;
  state={time:t,scene:s.id,index:i,mode:i===3?'historical_offline':i===4?'captured_ensemble':i===5?'missingness_demonstration':i===6||i===7||i===8?'hypothetical_demo':'brand_or_schema',
    calculation:MeiyuDecision.calculate({probability:.6,move_cost:cost,loss_without:1000,loss_after:100}),
    model_example:D.history.example,weather_fraction:D.weather.snapshot.windows[0].probability,weather_fetched_at:D.weather.snapshot.fetched_at_utc,
    beat:t/actualBeat,visual_beat:frameTime/B,source_audio_second:C.audio_start_seconds+t};return {...state};
}
const music=document.getElementById('music-audio'),playButton=document.getElementById('play'),seekControl=document.getElementById('seek'),viewer=document.getElementById('viewer'),buttons=[];
const stamp=t=>String(Math.floor(t/60)).padStart(2,'0')+':'+String(Math.floor(t%60)).padStart(2,'0');
for(const s of S){const b=document.createElement('button');b.textContent=s.label;b.onclick=()=>seek(s.start);buttons.push(b);document.getElementById('chapters').appendChild(b);}
function ui(){seekControl.value=now;document.getElementById('time').textContent=stamp(now)+' / '+stamp(Math.ceil(T));playButton.textContent=playing?'暂停':'播放';viewer.classList.toggle('playing',playing);buttons.forEach((b,i)=>b.classList.toggle('active',i===indexAt(Math.min(now,T-.001))));}
function sync(t){try{music.currentTime=clamp(t,0,T-.001);}catch{}}
function pause(){if(playing)now=clamp((performance.now()-started)/1000,0,T);playing=false;cancelAnimationFrame(raf);music.pause();ui();}
async function play(){if(playing)return pause();if(now>T-.05)now=0;sync(now);try{await music.play();started=performance.now()-now*1000;playing=true;document.getElementById('audio-status').textContent='现成器乐 · 无配音';ui();tick();}catch{music.pause();playing=false;document.getElementById('audio-status').textContent='请再次点击播放以开启配乐';ui();}}
function seek(t){now=clamp(t,0,T);sync(now);if(playing)started=performance.now()-now*1000;renderFrame(now);ui();if(now>=T)pause();}
function tick(){if(!playing)return;now=clamp((performance.now()-started)/1000,0,T);renderFrame(now);ui();if(Math.abs(music.currentTime-now)>.16)sync(now);if(now>=T){pause();return;}raf=requestAnimationFrame(tick);}
playButton.onclick=play;document.getElementById('center-play').onclick=play;document.getElementById('restart').onclick=()=>{pause();seek(0);play();};seekControl.oninput=e=>seek(+e.target.value);document.getElementById('music-volume').oninput=e=>music.volume=+e.target.value/100;document.getElementById('fullscreen').onclick=()=>document.fullscreenElement?document.exitFullscreen():viewer.requestFullscreen().catch(()=>{});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&playing)pause();});document.addEventListener('keydown',e=>{if(['INPUT','BUTTON','A'].includes(e.target.tagName))return;if(e.code==='Space'){e.preventDefault();play();}else if(e.code==='ArrowRight'){e.preventDefault();seek(S[Math.min(S.length-1,indexAt(now)+1)].start);}else if(e.code==='ArrowLeft'){e.preventDefault();seek(S[Math.max(0,indexAt(now)-1)].start);}});
window.MEIYU_FILM={canvas,ready:true,fps:30,duration:T,renderFrame,pause,play,seek,getState:()=>({...state}),getTextBounds:()=>bounds.map(b=>({...b})),timeline:S.map(s=>({id:s.id,start:s.start,end:s.end})),
  reuse:{library:'GSAP + Three.js original 169s geometry',version:gsap.version,legacy:legacy.metadata,entry:'GSAP + original Three.js render -> Canvas -> VideoFrame',timelineChildren:master.getChildren().length},audio:{music,mode:'instrumental_only',speechTracks:0,title:C.title,artist:C.artist,bpm:C.bpm},sync:C};
renderFrame(6*actualBeat);ui();
})();
