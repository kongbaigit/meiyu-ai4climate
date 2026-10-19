(()=>{'use strict';
const D=FILM_INPUT.evidence,T=FILM_INPUT.timeline,W=1920,H=1080,TAU=Math.PI*2;
const C={ink:'#1c2733',muted:'#657584',faint:'#8e9aa6',blue:'#087fce',cyan:'#30a6cf',teal:'#168e84',orange:'#e9874b',purple:'#7a82c6',light:'#e2e8ee',paper:'#f6f7f9'};
const FONT='"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif';
const canvas=document.querySelector('#film'),ctx=canvas.getContext('2d',{alpha:false});
const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
const mix=(a,b,t)=>a+(b-a)*t;
const smooth=(a,b,t)=>{const k=clamp((t-a)/(b-a));return k*k*(3-2*k)};
const expo=v=>v===1?1:1-2**(-10*clamp(v));
const rand=(i,k=0)=>{const v=Math.sin(i*127.1+k*311.7+17.13)*43758.5453123;return v-Math.floor(v)};
const scenes=T.scenes;
let textBounds=[],lastState={},rendering=false;
function at(t){let i=scenes.findIndex(s=>t<s.end);if(i<0)i=scenes.length-1;return{i,s:scenes[i],u:clamp(t-scenes[i].start,0,scenes[i].duration)}}
function costAt(u){return mix(10,95,smooth(6.4,10.4,u))}
function stateAt(t){const {i,s,u}=at(t);const cost=s.id==='cost'?costAt(u):10;const referenceVisible=s.id==='reveal'&&u>=3.5;return {time:clamp(t,0,T.duration),scene:s.id,sceneIndex:i,localTime:u,probability:D.probability,cost,threshold:cost/100,prepare:D.probability>=cost/100,referenceVisible,reference_mm:referenceVisible?D.reference_mm:null}}
function text(value,x,y,size=32,color=C.ink,weight=500,align='left',alpha=1){
 ctx.save();ctx.globalAlpha*=alpha;ctx.fillStyle=color;ctx.font=`${weight} ${size}px ${FONT}`;ctx.textAlign=align;ctx.textBaseline='alphabetic';
 const width=ctx.measureText(String(value)).width;ctx.fillText(String(value),x,y);textBounds.push({text:String(value),x:align==='center'?x-width/2:align==='right'?x-width:x,y:y-size,width,height:size*1.2});ctx.restore();
}
function paragraph(value,x,y,width=620,size=30,color=C.muted,lineHeight=46,weight=400){
 let line='',row=0;for(const ch of value){ctx.font=`${weight} ${size}px ${FONT}`;if(ch==='\n'||(line&&ctx.measureText(line+ch).width>width)){text(line,x,y+row*lineHeight,size,color,weight);line=ch==='\n'?'':ch;row++}else line+=ch}if(line)text(line,x,y+row*lineHeight,size,color,weight);return (row+1)*lineHeight;
}
function reveal(value,x,y,size,u,delay=0,color=C.ink,weight=700){const e=expo(clamp((u-delay)/1.05));ctx.save();ctx.beginPath();ctx.rect(x-8,y-size-10,780,size*1.35+20);ctx.clip();text(value,x,y+(1-e)*size*1.1,size,color,weight,'left',e);ctx.restore()}
function line(x1,y1,x2,y2,color,width=2,alpha=1){ctx.save();ctx.globalAlpha*=alpha;ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();ctx.restore()}
function roundRect(x,y,w,h,r,fill,stroke){ctx.beginPath();ctx.roundRect(x,y,w,h,r);if(fill){ctx.fillStyle=fill;ctx.fill()}if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=1.5;ctx.stroke()}}
function pill(value,x,y,color=C.blue,alpha=1){ctx.save();ctx.globalAlpha*=alpha;ctx.font=`600 24px ${FONT}`;const width=ctx.measureText(value).width+34;roundRect(x,y-31,width,45,22,color+'10',color+'22');text(value,x+17,y,24,color,550);ctx.restore();return width}
function droplet2D(x,y,scale,color){ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);ctx.beginPath();ctx.moveTo(0,-18);ctx.bezierCurveTo(-7,-7,-13,0,-13,8);ctx.bezierCurveTo(-13,25,13,25,13,8);ctx.bezierCurveTo(13,0,7,-7,0,-18);ctx.fillStyle=color;ctx.fill();ctx.restore()}

const glCanvas=document.createElement('canvas');glCanvas.width=W;glCanvas.height=H;
let renderer,camera,world,groups=[],actor,actorPositions,actorColors,webglError=null;
const models={},shadowObjects=[];
const palette={white:0xf8fafc,blue:0x168fcb,cyan:0x59b9d9,teal:0x38a798,orange:0xf1a06e,grey:0xc6d0db,purple:0x929ad4};
function material(color,extra={}){return new THREE.MeshPhysicalMaterial({color,metalness:.1,roughness:.35,clearcoat:1,clearcoatRoughness:.22,...extra})}
function box(group,x,y,z,w,h,d,color=palette.white,r=.08){
 const geometry=new THREE.BoxGeometry(w,h,d);const mesh=new THREE.Mesh(geometry,material(color));mesh.position.set(x,y,z);mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);return mesh;
}
function rounded(group,x,y,z,w,h,d,color=palette.white,r=.13){
 const shape=new THREE.Shape();const hw=w/2,hh=h/2,rr=Math.min(r,hw-.01,hh-.01);
 shape.moveTo(-hw+rr,-hh);shape.lineTo(hw-rr,-hh);shape.quadraticCurveTo(hw,-hh,hw,-hh+rr);shape.lineTo(hw,hh-rr);shape.quadraticCurveTo(hw,hh,hw-rr,hh);shape.lineTo(-hw+rr,hh);shape.quadraticCurveTo(-hw,hh,-hw,hh-rr);shape.lineTo(-hw,-hh+rr);shape.quadraticCurveTo(-hw,-hh,-hw+rr,-hh);
 const geometry=new THREE.ExtrudeGeometry(shape,{depth:d,bevelEnabled:true,bevelSegments:3,steps:1,bevelSize:.035,bevelThickness:.035,curveSegments:8});geometry.translate(0,0,-d/2);
 const mesh=new THREE.Mesh(geometry,material(color));mesh.position.set(x,y,z);mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);return mesh;
}
function cylinder(group,x,y,z,r,h,color=palette.blue){const mesh=new THREE.Mesh(new THREE.CylinderGeometry(r,r,h,64,1),material(color));mesh.position.set(x,y,z);mesh.castShadow=true;mesh.receiveShadow=true;group.add(mesh);return mesh}
function sphere(group,x,y,z,r,color=palette.blue,extra={}){const mesh=new THREE.Mesh(new THREE.SphereGeometry(r,32,20),material(color,extra));mesh.position.set(x,y,z);mesh.castShadow=true;group.add(mesh);return mesh}
function tube(group,points,color=palette.blue,r=.025){const curve=new THREE.CatmullRomCurve3(points.map(p=>new THREE.Vector3(...p)));const mesh=new THREE.Mesh(new THREE.TubeGeometry(curve,90,r,8,false),material(color,{roughness:.5}));group.add(mesh);return {mesh,curve}}
function ring(group,r,y,color,thickness=.05){const mesh=new THREE.Mesh(new THREE.TorusGeometry(r,thickness,12,96),material(color));mesh.rotation.x=Math.PI/2;mesh.position.y=y;group.add(mesh);return mesh}
function dropMesh(group,scale=1,color=palette.blue){
 const points=[new THREE.Vector2(0,-1.4),new THREE.Vector2(.55,-1.25),new THREE.Vector2(.85,-.85),new THREE.Vector2(.9,-.25),new THREE.Vector2(.75,.35),new THREE.Vector2(.48,.95),new THREE.Vector2(.15,1.6),new THREE.Vector2(0,1.95)];
 const mesh=new THREE.Mesh(new THREE.LatheGeometry(points,64),material(color,{metalness:.18,roughness:.2}));mesh.scale.setScalar(scale);group.add(mesh);mesh.castShadow=true;return mesh;
}
function makeGroup(){const g=new THREE.Group();g.position.x=4.5;world.add(g);groups.push(g);return g}
function init3D(){
 renderer=new THREE.WebGLRenderer({canvas:glCanvas,antialias:true,alpha:true,preserveDrawingBuffer:true,powerPreference:'high-performance'});renderer.setSize(W,H,false);renderer.setPixelRatio(1);renderer.setClearColor(0xf5f7fa,0);renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.13;renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
 world=new THREE.Scene();world.fog=new THREE.Fog(0xf5f7fa,33,90);camera=new THREE.PerspectiveCamera(38,W/H,.1,150);
 world.add(new THREE.HemisphereLight(0xffffff,0xbac9d7,2.2));world.add(new THREE.AmbientLight(0xffffff,.4));
 const key=new THREE.DirectionalLight(0xffffff,3.3);key.position.set(-7,16,11);key.castShadow=true;key.shadow.mapSize.set(2048,2048);key.shadow.camera.left=-17;key.shadow.camera.right=17;key.shadow.camera.top=17;key.shadow.camera.bottom=-17;key.shadow.normalBias=.04;key.shadow.bias=-.0001;world.add(key);
 const rim=new THREE.DirectionalLight(0xc9eaff,2.4);rim.position.set(12,7,-10);world.add(rim);
 const floor=new THREE.Mesh(new THREE.PlaneGeometry(160,160),new THREE.ShadowMaterial({opacity:.12}));floor.rotation.x=-Math.PI/2;floor.position.y=-.13;floor.receiveShadow=true;world.add(floor);
 buildModels();
 actorPositions=new Float32Array(2200*3);actorColors=new Float32Array(2200*3);const colors=[new THREE.Color(palette.orange),new THREE.Color(palette.teal),new THREE.Color(palette.blue)];for(let j=0;j<2200;j++){const color=colors[j%11===0?0:j%3===0?1:2];actorColors[j*3]=color.r;actorColors[j*3+1]=color.g;actorColors[j*3+2]=color.b}const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(actorPositions,3));geometry.setAttribute('color',new THREE.BufferAttribute(actorColors,3));
 actor=new THREE.Points(geometry,new THREE.PointsMaterial({size:.045,vertexColors:true,transparent:true,opacity:.5,depthWrite:false,sizeAttenuation:true}));actor.frustumCulled=false;world.add(actor);
 renderer.compile(world,camera);
}
function buildModels(){
 const shop=makeGroup();models.shop={group:shop,boxes:[]};
 rounded(shop,0,-.03,0,7.6,5.2,.16,palette.white,.15).rotation.x=-Math.PI/2;
 box(shop,0,1.8,-1.35,5.7,3.5,.16);box(shop,-2.8,1.7,0,.15,3.4,2.8);box(shop,2.8,1.7,0,.15,3.4,2.8);
 rounded(shop,0,3.65,.05,6.3,.32,3.4,palette.white,.15);rounded(shop,0,2.8,1.55,5.75,.62,.15,palette.blue,.1);
 for(let i=0;i<6;i++)box(shop,-2.35+i*.94,3.25,1.82,.9,.16,1.3,i%2?palette.white:palette.teal);
 const glass=rounded(shop,1.2,1.38,1.46,2.6,2.42,.05,palette.cyan,.04);glass.material=material(palette.cyan,{transparent:true,opacity:.16,depthWrite:false,metalness:0,roughness:.2});glass.castShadow=false;
 box(shop,-1.45,.68,.5,2.3,.12,1.7,palette.grey);box(shop,-2.42,.31,.5,.1,.64,1.5,palette.grey);box(shop,-.48,.31,.5,.1,.64,1.5,palette.grey);
 for(let i=0;i<8;i++){const b=rounded(shop,-2.05+(i%3)*.65, .5+Math.floor(i/3)*.55,.65+((i%2)*.05),.56,.48,.6,i%3===0?palette.orange:palette.white,.07);models.shop.boxes.push(b)}
 for(let i=0;i<5;i++)sphere(shop,-.8+i*.5,5.65+Math.sin(i)*.18,-.5,.76-i*.055,palette.white,{roughness:.6});
 const data=makeGroup();models.data={group:data};
 const geo=new THREE.BoxGeometry(.32,.085,.32),mat=material(palette.white,{roughness:.5});const tiles=new THREE.InstancedMesh(geo,mat,D.sample_count);tiles.receiveShadow=true;tiles.castShadow=false;data.add(tiles);models.data.tiles=tiles;
 const sourcePaths=[];
 for(const x of [-3,3])sourcePaths.push(tube(data,[[x,4.8,-3],[x,4.4,0],[x*.5,3,2],[0,.2,2.5]],x<0?palette.blue:palette.teal,.035));
 models.data.paths=sourcePaths;
 models.data.packets=[];for(let i=0;i<16;i++)models.data.packets.push(sphere(data,0,0,0,.075,i%2?palette.teal:palette.blue));
 const gauge=makeGroup();models.gauge={group:gauge};
 const back=new THREE.Mesh(new THREE.TorusGeometry(2.65,.11,16,128),material(0xe5ebf1));back.position.set(0,2.95,0);gauge.add(back);
 const arc=new THREE.Mesh(new THREE.TorusGeometry(2.65,.14,16,128,TAU*D.probability),material(palette.blue,{metalness:.16}));arc.position.set(0,2.95,.01);arc.rotation.z=Math.PI/2;arc.scale.x=-1;gauge.add(arc);models.gauge.arc=arc;
 const rimGauge=new THREE.Mesh(new THREE.TorusGeometry(2.96,.015,8,128),material(0xb8cedc));rimGauge.position.set(0,2.95,-.03);gauge.add(rimGauge);
 const threshold=sphere(gauge,0,0,.1,.16,palette.orange);models.gauge.threshold=threshold;
 ring(gauge,3.5,.03,0xd6e2eb,.018);
 const ref=makeGroup();models.reference={group:ref,levels:[]};
 for(let i=0;i<2;i++){
  const x=(i-.5)*3.2;const vessel=cylinder(ref,x,2.65,0,.95,5.3,palette.cyan);vessel.material=material(0xd7e9f0,{transparent:true,opacity:.13,depthWrite:false,roughness:.5});vessel.castShadow=false;
  const liquid=cylinder(ref,x,.1,0,.86,.1,i?palette.blue:palette.orange);models.reference.levels.push(liquid);
  for(let j=0;j<=6;j++){const r=ring(ref,.98,j*5.3/6,0xaabdcf,.012);r.position.x=x}
  const base=cylinder(ref,x,.05,0,1.15,.13,palette.white);
 }
 const split=makeGroup();models.split={group:split};
 const splitTiles=new THREE.InstancedMesh(geo,mat.clone(),D.sample_count);splitTiles.receiveShadow=true;split.add(splitTiles);models.split.tiles=splitTiles;
 const bars=makeGroup();models.bars={group:bars,items:[]};
 const methods=['training_climatology','raw_nwp_rule','logistic_rain','logistic_weather'];
 methods.forEach((method,i)=>{const x=(i-1.5)*2.2;const b=rounded(bars,x,.1,0,1.4,.2,1.7,method===D.selected_method?palette.blue:i===3?palette.purple:palette.grey,.1);models.bars.items.push({mesh:b,method,x});rounded(bars,x,-.02,0,1.8,.1,2.15,palette.white,.1)});
 const failures=makeGroup();models.failures={group:failures};
 const failTiles=new THREE.InstancedMesh(new THREE.BoxGeometry(.34,.11,.34),material(palette.white),D.test_outcomes.length);failures.add(failTiles);models.failures.tiles=failTiles;
 const calendar=makeGroup();models.calendar={group:calendar};
 const months=9,days=[];const known=new Map(D.temporal_observations.map(o=>[o.date,o]));
 for(let month=0;month<months;month++){const n=new Date(Date.UTC(2026,month+1,0)).getUTCDate();for(let d=1;d<=n;d++){const date=`2026-${String(month+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;days.push({month,day:d,known:known.get(date),date})}}
 const calTiles=new THREE.InstancedMesh(new THREE.BoxGeometry(.62,.09,.22),material(palette.white),days.length);calendar.add(calTiles);models.calendar.tiles=calTiles;models.calendar.days=days;
 const future=makeGroup();models.future={group:future,plates:[],nodes:[]};
 for(let i=0;i<4;i++){const x=(i%2?1:-1)*1.2,y=.55+i*1.3,z=-i*.7;const p=rounded(future,x,y,z,3.8,2.4,.13,palette.white,.16);p.rotation.x=-Math.PI/2;models.future.plates.push(p);models.future.nodes.push(sphere(future,x-1.1,y+.2,z,.15,[palette.blue,palette.teal,palette.orange,palette.purple][i]))}
 models.future.path=tube(future,[[-2,.7,1],[1.3,1.9,-.7],[-1.1,3.1,-1.4],[1.1,4.5,-2.1]],palette.blue,.04);
 const logo=makeGroup();logo.position.x=0;models.logo={group:logo};models.logo.drop=dropMesh(logo,.8);models.logo.drop.position.y=3.9;
 groups.forEach(g=>g.visible=false);
}
const tempObject=new THREE.Object3D(),tempColor=new THREE.Color();
function tilePosition(i,split=false){const c=i%20,r=Math.floor(i/20),isTrain=i<276,isVal=i<396;const lift=split?(isTrain?0:isVal?1.1:2.2):0;return [(c-9.5)*.4,.13+lift,(r-15.5)*.4]}
function particleTarget(i,scene,t){
 const a=rand(i),b=rand(i,1),c=rand(i,2);let x=0,y=0,z=0;
 if(scene===0){x=(a-.5)*10;y=7-((b*9+t*(1.1+c*1.5))%9);z=(c-.5)*8}
 else if(scene===1){const p=tilePosition(i%636);const f=smooth(1,6,t);x=mix((a-.5)*13,p[0],f);y=mix(2+b*6,p[1]+.16,f);z=mix((c-.5)*13,p[2],f)}
 else if(scene===2||scene===3){const theta=a*TAU+t*.15;const radius=3.4+b*1.6;x=Math.cos(theta)*radius;y=2.95+Math.sin(theta)*radius;z=(c-.5)*2.2}
 else if(scene===4){x=(a<.5?-1.6:1.6)+(b-.5)*1.6;y=6-((c*8+t*1.8)%7);z=(rand(i,4)-.5)*1.6}
 else if(scene===5){const p=tilePosition(i%636,true);x=p[0];y=mix(.13,p[1],smooth(2,7,t))+.16+Math.sin(t*.8+i*.03)*.045;z=p[2]}
 else if(scene===6){const j=i%4,m=models.bars.items[j].method,h=D.test_metrics[m].brier/.07*5;x=(j-1.5)*2.2+(a-.5)*.8;y=(b*h+t*.3)%h;z=(c-.5)*1.2}
 else if(scene===7){const j=i%240;x=(j%20-9.5)*.44;y=.23+Math.sin(t+i*.3)*.03;z=(Math.floor(j/20)-5.5)*.44}
 else if(scene===8){const d=models.calendar.days[i%273];x=(d.month-4)*.94;y=d.known?.27:.04;z=(d.day-16)*.3}
 else {const theta=a*TAU,r=Math.sqrt(b),ny=c*3.4-1.5,width=.95*(1-Math.max(0,ny)/2.1);x=Math.cos(theta)*width*r;y=ny+3.8;z=Math.sin(theta)*width*r;const e=smooth(9,15,t);x=mix((a-.5)*10,x,e);y=mix(1+b*5,y,e);z=mix((c-.5)*7,z,e)}
 return [x+(scene===9?mix(4.5,0,smooth(10,15,t)):4.5),y,z];
}
const poses=[[12,9,23],[10,14,24],[9,7,24],[10,8,24],[11,11,24],[12,16,25],[13,10,24],[10,15,23],[10,17,25],[11,10,24]];
function modelFrame(i,u){
 groups.forEach(g=>g.visible=false);const enter=expo(clamp(u/1.6));const k=i;
 const camCurrent=poses[i],camBefore=poses[Math.max(0,i-1)],e=smooth(0,2.3,u);const drift=Math.sin(u/scenes[i].duration*Math.PI)*1.1;
 camera.position.set(mix(camBefore[0],camCurrent[0],e)+drift,mix(camBefore[1],camCurrent[1],e),mix(camBefore[2],camCurrent[2],e));
 const closing=i===9?smooth(10,15,u):0;camera.lookAt(mix(0,0,closing),mix(1.25,3,closing),0);
 const group=[models.shop.group,models.data.group,models.gauge.group,models.gauge.group,models.reference.group,models.split.group,models.bars.group,models.failures.group,models.calendar.group,models.future.group][i];group.visible=true;group.scale.setScalar(.93+.07*enter);group.rotation.y=Math.sin(u*.1)*.025;
 if(i===0){models.shop.boxes.forEach((b,j)=>{b.position.y=.36+Math.floor(j/3)*.5+mix(0,.45,smooth(6+j*.14,9+j*.14,u))});group.rotation.y=-.3+u*.008}
 if(i===1||i===5){const obj=i===1?models.data:models.split;for(let j=0;j<636;j++){const p=tilePosition(j,i===5);const rise=expo(clamp((u-1-j/636*1.7)/1.5));const scan=1-smooth(0,.07,Math.abs(j/636-(u*.13)%1));const base=i===5?mix(.13,p[1],smooth(2,7,u)):p[1]+scan*.06;tempObject.position.set(p[0],base+(1-rise)*(2+rand(j)),p[2]);tempObject.scale.setScalar(rise);tempObject.rotation.set(0,0,0);tempObject.updateMatrix();obj.tiles.setMatrixAt(j,tempObject.matrix);tempColor.setHex(i===5?(j<276?palette.blue:j<396?palette.orange:palette.teal):scan>.5?palette.blue:palette.white);obj.tiles.setColorAt(j,tempColor)}obj.tiles.instanceMatrix.needsUpdate=true;obj.tiles.instanceColor.needsUpdate=true;group.rotation.y=-.2+Math.sin(u*.16)*.055;if(i===1)models.data.packets.forEach((packet,j)=>packet.position.copy(models.data.paths[j%2].curve.getPointAt((u*.21+j/16)%1)))}
 if(i===2||i===3){models.gauge.threshold.visible=i===3;const p=D.probability*expo(clamp(u/2.2));models.gauge.arc.geometry.setDrawRange(0,Math.floor(models.gauge.arc.geometry.index.count*p/D.probability/3)*3);const cost=costAt(u),angle=TAU*cost/100;models.gauge.threshold.position.set(Math.sin(angle)*2.65,2.95+Math.cos(angle)*2.65,.15);group.rotation.y=-.25+Math.sin(u/scenes[i].duration*Math.PI)*.48}
 if(i===4){models.reference.levels.forEach((m,j)=>{const h=(j?D.reference_mm:D.forecast_mm)/60*4.8*expo(clamp((u-(j?3.5:.5))/2));m.scale.y=Math.max(.001,h/.1);m.scale.x=1+Math.sin(u*1.8+j)*.004;m.scale.z=1-Math.sin(u*1.8+j)*.004;m.position.y=h/2+.13});group.rotation.y=-.3+u*.029}
 if(i===6){models.bars.items.forEach((item,j)=>{const h=D.test_metrics[item.method].brier/.07*5*expo(clamp((u-1-j*.22)/1.9));item.mesh.scale.y=Math.max(.001,h/.2);item.mesh.position.y=h/2+.08});group.rotation.y=-.15}
 if(i===7){for(let j=0;j<D.test_outcomes.length;j++){const outcome=D.test_outcomes[j].outcome,highlight=u>3;const rise=highlight&&(outcome==='fn'||outcome==='fp')?mix(.13,.75,smooth(3,5,u)):.13;tempObject.position.set((j%20-9.5)*.44,rise,(Math.floor(j/20)-5.5)*.44);tempObject.scale.set(1,1,1);tempObject.rotation.set(0,0,0);tempObject.updateMatrix();models.failures.tiles.setMatrixAt(j,tempObject.matrix);tempColor.setHex(!highlight?palette.white:outcome==='fn'?0xd67666:outcome==='fp'?palette.orange:outcome==='tp'?palette.blue:0xe6ebf0);models.failures.tiles.setColorAt(j,tempColor)}models.failures.tiles.instanceMatrix.needsUpdate=true;models.failures.tiles.instanceColor.needsUpdate=true;group.rotation.y=-.25}
 if(i===8){models.calendar.days.forEach((d,j)=>{const observed=Boolean(d.known),rise=expo(clamp((u-.7-d.month*.14)/1.6));tempObject.position.set((d.month-4)*.94,(observed?.2:.02)*rise,(d.day-16)*.3);tempObject.scale.set(1,rise,1);tempObject.rotation.set(0,0,0);tempObject.updateMatrix();models.calendar.tiles.setMatrixAt(j,tempObject.matrix);tempColor.setHex(observed?(d.known.event?palette.orange:palette.blue):0xe6ebf0);models.calendar.tiles.setColorAt(j,tempColor)});models.calendar.tiles.instanceMatrix.needsUpdate=true;models.calendar.tiles.instanceColor.needsUpdate=true;group.rotation.y=-.15}
 if(i===9){models.future.plates.forEach((p,j)=>{p.scale.setScalar(expo(clamp((u-.4-j*.45)/1.6))*(1-closing));models.future.nodes[j].scale.setScalar(1-closing)});group.visible=closing<.999;models.logo.group.visible=closing>.01;models.logo.group.scale.setScalar(closing);models.logo.drop.rotation.y=u*.13}
 const blend=smooth(0,1.5,u);
 for(let j=0;j<2200;j++){const now=particleTarget(j,i,u),before=particleTarget(j,Math.max(0,i-1),i?scenes[i-1].duration:0);for(let a=0;a<3;a++)actorPositions[j*3+a]=mix(before[a],now[a],blend)}
 actor.geometry.attributes.position.needsUpdate=true;actor.material.opacity=i===1||i===5||i===7||i===8?.2:.45;
 renderer.render(world,camera);
}
function project(group,x,y,z){const p=new THREE.Vector3(x,y,z);group.localToWorld(p);p.project(camera);return{x:(p.x*.5+.5)*W,y:(-.5*p.y+.5)*H}}
function worldLabel(group,value,x,y,z,color=C.muted,size=25,weight=500){const p=project(group,x,y,z);text(value,p.x,p.y,size,color,weight,'center')}
function common(t,index){
 droplet2D(121,66,.54,C.blue);text('梅雨有数',145,78,29,C.ink,650);text('AI FOR CLIMATE',1788,65,19,C.muted,550,'right');text('历史离线原型',1788,94,18,C.faint,400,'right');
 const start=116,total=1685,gap=9,width=(total-gap*9)/10;scenes.forEach((s,j)=>{const progress=clamp((t-s.start)/s.duration);line(start+j*(width+gap),1025,start+j*(width+gap)+width,1025,'#e1e7ed',4);if(progress>0)line(start+j*(width+gap),1025,start+j*(width+gap)+width*progress,1025,C.blue,4);text(s.label,start+j*(width+gap),1056,18,j===index?C.blue:C.faint,j===index?600:400)});
}
function kicker(index,u){text(`${String(index+1).padStart(2,'0')}  /  ${scenes[index].label}`,122,210,23,C.blue,600,'left',expo(clamp(u/1.1)))}
function heads(lines,u,size=68){lines.forEach((s,i)=>reveal(s,118,315+i*(size*1.3),size,u,.25+i*.18))}
function disclaimer(value,y=835){paragraph(value,122,y,650,24,C.muted,37,400)}
function mappingCurve(u){
 const x=128,y=760,w=535,h=145,par=D.logistic_rain;
 line(x,y,x+w,y,'#cbd6df',2);line(x,y,x,y-h,'#cbd6df',2);
 text('0',x-15,y+34,20,C.faint,400);text('100 mm',x+w,y+34,20,C.faint,400,'right');text('100%',x-5,y-h-15,20,C.faint,400);
 const value=rain=>1/(1+Math.exp(-(Math.log1p(rain)-par.scaler_mean[0])/par.scaler_scale[0]*par.coefficients_after_scaled_features[0]-par.intercept));
 const appear=expo(clamp((u-2)/2.5));ctx.beginPath();for(let j=0;j<=100*appear;j++){const xx=x+j/100*w,yy=y-value(j)*h;j?ctx.lineTo(xx,yy):ctx.moveTo(xx,yy)}ctx.strokeStyle=C.blue;ctx.lineWidth=4;ctx.stroke();
 if(u>4.2){const px=x+D.forecast_mm/100*w,py=y-D.probability*h;line(px,y,px,py,C.blue,1.5,.3);ctx.beginPath();ctx.arc(px,py,7,0,TAU);ctx.fillStyle=C.blue;ctx.fill();text('输入 52.5 mm',px+14,py-42,23,C.blue,550)}
}
function hud(i,u){
 kicker(i,u);const opacity=expo(clamp((u-.3)/1.4));ctx.save();
 if(i===0){
  const second=smooth(7.4,9,u);ctx.save();ctx.globalAlpha=1-second;heads(['下雨之前，','准备值得吗？'],u,83);paragraph('一次准备要花多少精力，\n需要一个能解释清楚的判断。',122,570,650,32,C.muted,52);ctx.restore();
  if(second>0){ctx.save();ctx.globalAlpha=second;reveal('梅雨有数',118,375,112,u,7.5);paragraph('解释降雨概率与准备成本\n面向整理易受潮货物的小商户',125,510,650,33,C.muted,54);pill('气候适应 · 用户场景假设',125,666,C.teal);ctx.restore()}
  disclaimer('目标用户需求尚待验证。\n三维商铺为场景示意，未开展真实商户试点。');
  if(webglError===null)worldLabel(models.shop.group,'易受潮货物',-1.15,1.5,1.8,C.blue,23,550);
 }else if(i===1){
  heads(['先核查来源，','再解释概率。'],u,72);text(Math.round(636*expo(clamp((u-1.5)/2))).toString(),118,632,152,C.ink,650);text('配对日窗口',125,686,31,C.muted,500);
  pill('NOAA SSOD',125,768,C.blue);pill('Open-Meteo',338,768,C.teal);
  disclaimer('每个窗口保留来源快照与引用。\n缺失与不完整参考数据不会补成零。',850);
  if(!webglError&&u>4){worldLabel(models.data.group,'参考降水',-3,5.05,-3,C.blue,25);worldLabel(models.data.group,'合成预报',3,5.05,-3,C.teal,25)}
 }else if(i===2){
  heads(['把预报雨量，','映射为概率。'],u,72);pill('2025.06.01 · 萧山机场',125,520,C.blue);text('冻结参数的概率映射',128,559,24,C.muted,500);mappingCurve(u);
  disclaimer('目标：参考日降水 ≥ 25 mm。\n名义UTC日；北京08:00至次日08:00。',845);
  if(!webglError){const p=project(models.gauge.group,0,2.95,.2);text((D.probability*100*expo(clamp(u/2.2))).toFixed(1)+'%',p.x,p.y+28,102,C.blue,650,'center');text('模型估计概率',p.x,p.y+78,27,C.muted,450,'center');text('没有表示门店积水概率',p.x,p.y+315,26,C.muted,500,'center')}
 }else if(i===3){
  heads(['准备的门槛，','随成本改变。'],u,72);const cost=costAt(u),yes=D.probability>=cost/100;
  text(Math.round(cost).toString(),120,630,151,C.ink,650);text('单位 / 次',325,626,33,C.muted,400);text('假设准备成本',128,686,29,C.muted,450);
  pill(yes?'情景选择：准备':'情景选择：暂不准备',125,768,yes?C.teal:C.orange);
  disclaimer('假设未准备且事件发生损失为100单位，\n准备能完全避损。两项假设均待实测。',850);
  if(!webglError){const p=project(models.gauge.group,0,2.95,.2);text('67.9%',p.x,p.y+25,102,C.blue,650,'center');text('概率保持不变',p.x,p.y+75,27,C.muted,450,'center');text('情景门槛 '+Math.round(cost)+'%',p.x,p.y+315,34,yes?C.teal:C.orange,600,'center');}
 }else if(i===4){
  heads(['先看概率，','再揭晓参考。'],u,72);const appear=expo(clamp((u-3.5)/2));text(u<3.5?'—':(D.reference_mm*appear).toFixed(0),120,635,154,C.blue,650);if(u>=3.5)text('mm',335,632,45,C.blue,450);text(u<3.5?'参考降水待揭晓':'该日参考降水',127,692,29,C.muted,450);
  text('原始预报 52.5 mm',127,765,36,C.muted,500);disclaimer('单日案例只解释过程。\n判断模型表现需要看整个测试段。',850);
  if(!webglError){worldLabel(models.reference.group,'预报 52.5',-1.6,5.8,0,C.orange,27,600);worldLabel(models.reference.group,u<3.5?'参考待揭晓':'参考 29',1.6,5.8,0,C.blue,27,600)}
 }else if(i===5){
  heads(['训练、验证、测试，','沿时间分开。'],u,62);const rows=[['2024','训练',276,C.blue],['2025.01—04','验证',120,C.orange],['2025.05—12','测试',240,C.teal]];
  rows.forEach((r,j)=>{const yy=540+j*97;line(126,yy+27,712,yy+27,'#e0e6ec',1);text(r[0],127,yy,25,C.muted,450);text(r[1],350,yy,28,r[3],600);text(r[2].toString(),685,yy+2,51,C.ink,600,'right')});
  disclaimer('填充、标准化与拟合只用训练段。\n测试段不参与参数与方法选择。',850);
 }else if(i===6){
  heads(['评分公开，','选择也公开。'],u,72);text('0.0455',119,632,124,C.blue,650);text('验证选中的降水模型 · 测试Brier',127,692,27,C.muted,500);pill('240日 / 18个参考事件',125,768,C.blue);
  disclaimer('Brier越低越好。温湿度模型测试更低，\n验证未选中，因此保留原推荐方法。',850);
  if(!webglError){const names=['固定事件率','25 mm规则','降水模型','加温湿度'];models.bars.items.forEach((item,j)=>{const h=D.test_metrics[item.method].brier/.07*5;worldLabel(models.bars.group,D.test_metrics[item.method].brier.toFixed(4),item.x,h+.68,0,j===2?C.blue:C.muted,31,j===2?650:500);worldLabel(models.bars.group,names[j],item.x,-.14,1.55,j===2?C.blue:C.muted,23,500)});}
 }else if(i===7){
  heads(['把失误，','一起保留下来。'],u,72);text('6',120,635,149,'#cf786b',650);text('漏掉的事件',233,624,30,C.muted,500);text('9',420,635,149,C.orange,650);text('误报日',538,624,30,C.muted,500);pill('固定情景门槛 10%',125,740,C.muted);
  disclaimer('模型保持原始连续雨量排序，学习概率映射。\n参考可能低报；少事件不足以证明稳定运营。',820);
  if(!webglError){text('240个测试日，每格对应1日',1315,444,25,C.muted,500,'center');text('命中12 · 漏报6 · 误报9',1315,833,25,C.muted,500,'center');}
 }else if(i===8){
  heads(['缺测的地方，','不写成无雨。'],u,72);text('85',120,622,143,C.blue,650);text('/ 273 日',330,620,48,C.muted,450);text('完整配对仅在1—3月 · 1个事件',127,686,29,C.muted,500);pill('4—9月缺少完整参考',125,768,C.orange);
  disclaimer('尚未补上2026梅雨表现验证。\n宁波因参考降水缺失暂停，未计算迁移指标。',850);
  if(!webglError){for(let j=0;j<9;j++)worldLabel(models.calendar.group,String(j+1)+'月',(j-4)*.94,.25,-5.2,j<3?C.blue:C.faint,24,500);}
 }else if(i===9){
  const closing=smooth(10,14,u);ctx.save();ctx.globalAlpha=1-closing;heads(['下一步，','用90天验证。'],u,76);paragraph('先验证用户能否理解，\n再核实真实预报获取与影子运行。',125,560,650,32,C.muted,54);disclaimer('当前没有真实商户避损或减排收益证据。\n90天验证安排尚待团队执行。',820);
  if(!webglError&&closing<.5){const names=['确认用户','理解测试','获取与影子运行','复查与决定'];models.future.plates.forEach((p,j)=>worldLabel(models.future.group,names[j],p.position.x,p.position.y+.55,p.position.z,C.muted,25,550))}ctx.restore();
  if(closing>0){ctx.save();ctx.globalAlpha=closing;text('梅雨有数',960,718,112,C.ink,700,'center');text('公开数据与可复现的气候适应原型',960,785,34,C.muted,450,'center');text('原创代码动画与配乐 · 自动旁白 · 材料工作稿',960,851,23,C.faint,450,'center');ctx.restore()}
 }
 ctx.restore();
}
function caption(t){const {s}=at(t);const local=t-s.speech_start;if(local<0||local>s.speech_duration)return;const clauses=s.text.match(/[^。！？]+[。！？]?/g)||[s.text],total=clauses.reduce((n,x)=>n+x.length,0);let offset=0,chosen=clauses.at(-1);for(const clause of clauses){const d=s.speech_duration*clause.length/total;if(local<offset+d){chosen=clause;break}offset+=d}ctx.save();ctx.fillStyle='rgba(246,248,250,.94)';ctx.fillRect(80,913,1760,89);ctx.font=`450 28px ${FONT}`;const lines=[];let current='';for(const ch of chosen){if(ctx.measureText(current+ch).width>1570){lines.push(current);current=ch}else current+=ch}if(current)lines.push(current);lines.forEach((value,j)=>text(value,960,949+j*38,28,'#3d4e5e',450,'center'));ctx.restore()}
function fallback(i,u){const g=ctx.createRadialGradient(1350,490,20,1350,490,370);g.addColorStop(0,'#168fcb22');g.addColorStop(1,'#168fcb00');ctx.fillStyle=g;ctx.fillRect(850,150,1000,700);if(i===2||i===3){ctx.strokeStyle=C.blue;ctx.lineWidth=12;ctx.beginPath();ctx.arc(1350,490,220,-Math.PI/2,-Math.PI/2+TAU*D.probability);ctx.stroke();text('67.9%',1350,525,100,C.blue,600,'center')}else droplet2D(1350,450,7,C.blue);text('三维渲染不可用，数字与旁白仍可查看',1350,780,24,C.muted,400,'center')}
function renderFrame(t,options={}){
 if(rendering)return;rendering=true;try{t=clamp(Number(t)||0,0,T.duration);textBounds=[];const {i,u}=at(t);const bg=ctx.createLinearGradient(0,0,W,H);bg.addColorStop(0,'#f9fafc');bg.addColorStop(1,'#f2f5f8');ctx.fillStyle=bg;ctx.fillRect(0,0,W,H);
 if(!webglError){modelFrame(i,u);ctx.drawImage(glCanvas,0,0,W,H)}else fallback(i,u);
 const wash=ctx.createLinearGradient(65,0,980,0);wash.addColorStop(0,'#f8fafcfb');wash.addColorStop(.73,'#f8fafce8');wash.addColorStop(1,'#f8fafc00');ctx.fillStyle=wash;ctx.fillRect(0,120,980,790);
 hud(i,u);caption(t);common(t,i);lastState={...stateAt(t),textBounds:textBounds.map(x=>({...x})),webgl:!webglError};
 }finally{rendering=false}
}
try{init3D()}catch(error){webglError=error.message;console.warn('WebGL轻量回退：'+webglError)}

let currentTime=5.5,playing=false,wallStart=0,startTime=0,audioContext=null,voiceGain=null,musicGain=null,audioBuffers=null,audioNodes=[],audioGeneration=0,audioStarted=false;
const seek=document.querySelector('#seek'),playButton=document.querySelector('#play'),viewer=document.querySelector('#viewer');
seek.max=T.duration;
scenes.forEach((s,i)=>{const b=document.createElement('button');b.textContent=`${String(i+1).padStart(2,'0')} ${s.label}`;b.addEventListener('click',()=>setTime(s.start+1.4));b.dataset.scene=s.id;document.querySelector('#chapters').appendChild(b)});
const format=t=>`${String(Math.floor(t/60)).padStart(2,'0')}:${String(Math.floor(t%60)).padStart(2,'0')}`;
function refreshUI(){seek.value=currentTime;document.querySelector('#time').textContent=`${format(currentTime)} / ${format(T.duration)}`;const {i,s}=at(currentTime);document.querySelector('#now').textContent=`${String(i+1).padStart(2,'0')}　${s.label}　·　${s.text}`;document.querySelectorAll('#chapters button').forEach((b,j)=>{b.classList.toggle('active',j===i);b.setAttribute('aria-current',j===i?'true':'false')});playButton.textContent=playing?'暂停':'播放';viewer.classList.toggle('playing',playing);canvas.setAttribute('aria-label',`梅雨有数，第${i+1}章，${s.label}，${format(currentTime)}`)}
function decodeBase64(value){const s=atob(value),raw=new Uint8Array(s.length);for(let i=0;i<s.length;i++)raw[i]=s.charCodeAt(i);return raw.buffer}
async function initAudio(){if(!audioContext){audioContext=new (window.AudioContext||window.webkitAudioContext)();voiceGain=audioContext.createGain();musicGain=audioContext.createGain();voiceGain.connect(audioContext.destination);musicGain.connect(audioContext.destination);voiceGain.gain.value=Number(document.querySelector('#voice-volume').value)/100;musicGain.gain.value=Number(document.querySelector('#music-volume').value)/100;audioBuffers=Promise.all([audioContext.decodeAudioData(decodeBase64(FILM_INPUT.voice)),audioContext.decodeAudioData(decodeBase64(FILM_INPUT.music))])}await audioContext.resume();return audioBuffers}
function stopAudio(){audioGeneration++;audioNodes.forEach(n=>{try{n.stop()}catch{}});audioNodes=[];audioStarted=false}
async function startAudio(offset){const generation=audioGeneration;try{const buffers=await initAudio();if(generation!==audioGeneration||!playing)return;const progressed=clamp(currentTime,0,T.duration);buffers.forEach((buffer,i)=>{if(progressed>=buffer.duration)return;const source=audioContext.createBufferSource();source.buffer=buffer;source.connect(i?musicGain:voiceGain);source.start(0,progressed);audioNodes.push(source)});audioStarted=true;document.querySelector('#audio-status').textContent='旁白与原创配乐已开启'}catch(error){document.querySelector('#audio-status').textContent='音频未能开启，可继续观看画面';console.warn(error.message)}}
function pause(){if(playing){currentTime=clamp(startTime+(performance.now()-wallStart)/1000,0,T.duration)}playing=false;stopAudio();renderFrame(currentTime);refreshUI()}
function play(){if(currentTime>=T.duration-.03)currentTime=0;playing=true;wallStart=performance.now();startTime=currentTime;stopAudio();startAudio(currentTime);refreshUI()}
function setTime(t){currentTime=clamp(Number(t),0,T.duration);if(playing){wallStart=performance.now();startTime=currentTime;stopAudio();startAudio(currentTime)}renderFrame(currentTime);refreshUI()}
playButton.addEventListener('click',()=>playing?pause():play());document.querySelector('#center-play').addEventListener('click',()=>{setTime(0);play()});document.querySelector('#restart').addEventListener('click',()=>{setTime(0);play()});seek.addEventListener('input',e=>setTime(e.target.value));
document.querySelector('#voice-volume').addEventListener('input',e=>{if(voiceGain)voiceGain.gain.value=Number(e.target.value)/100});document.querySelector('#music-volume').addEventListener('input',e=>{if(musicGain)musicGain.gain.value=Number(e.target.value)/100});
document.querySelector('#fullscreen').addEventListener('click',()=>document.fullscreenElement?document.exitFullscreen():viewer.requestFullscreen?.());
document.addEventListener('keydown',e=>{if(['INPUT','BUTTON'].includes(e.target.tagName))return;if(e.code==='Space'){e.preventDefault();playing?pause():play()}else if(e.code==='ArrowRight'){e.preventDefault();const {i}=at(currentTime);setTime(scenes[Math.min(i+1,scenes.length-1)].start+.8)}else if(e.code==='ArrowLeft'){e.preventDefault();const {i}=at(currentTime);setTime(scenes[Math.max(0,i-1)].start+.8)}});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&playing)pause()});
function tick(){if(playing){currentTime=clamp(startTime+(performance.now()-wallStart)/1000,0,T.duration);renderFrame(currentTime);refreshUI();if(currentTime>=T.duration-.001)pause()}requestAnimationFrame(tick)}
renderFrame(currentTime);refreshUI();requestAnimationFrame(tick);
window.MEIYU_FILM={canvas,duration:T.duration,fps:30,renderFrame,pause,play,seek:setTime,stateAt,getState:()=>lastState,getAudioState:()=>({context:audioContext?.state||'uninitialized',playing,audioStarted,voices:audioNodes.length,currentTime}),getRendererInfo:()=>({webgl:!webglError,error:webglError,library:THREE.REVISION,geometries:renderer?.info.memory.geometries}),ready:true};
})();
