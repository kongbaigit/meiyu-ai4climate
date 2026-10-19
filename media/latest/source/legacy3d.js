/*
 * Three.js geometry extracted from the 169 s native source.
 * The factory owns the renderer and has no player, UI, text, or audio path.
 */
(()=>{
  'use strict';
  window.createMeiyuLegacy3D=function createMeiyuLegacy3D(evidence,timeline,options={}){
    if(!evidence||!timeline) throw new TypeError('legacy3d需要冻结的evidence和timeline');
    const THREE=window.THREE;
    if(!THREE||typeof THREE.WebGLRenderer!=='function') throw new Error('Three.js 0.160.1未加载');
    const D=evidence,T=timeline,W=Number(options.width||1920),H=Number(options.height||1080),TAU=Math.PI*2;
    const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
    const mix=(a,b,t)=>a+(b-a)*t;
    const smooth=(a,b,t)=>{const k=clamp((t-a)/(b-a));return k*k*(3-2*k)};
    const expo=v=>v===1?1:1-2**(-10*clamp(v));
    const rand=(i,k=0)=>{const v=Math.sin(i*127.1+k*311.7+17.13)*43758.5453123;return v-Math.floor(v)};
    const scenes=T.scenes;const glCanvas=document.createElement('canvas');glCanvas.width=W;glCanvas.height=H;
let renderer,camera,world,groups=[],actor,actorPositions,actorColors,webglError=null;
const models={},shadowObjects=[];
const palette={white:0xf1f1df,blue:0x286c60,cyan:0x99c9b0,teal:0x5d9b7c,orange:0xe8be78,grey:0xb9c5b2,purple:0x93ad9a};
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
    function render(index,u=0){
      if(!Number.isInteger(index)||index<0||index>=scenes.length) throw new RangeError(`legacy3d场景索引无效: ${index}`);
      if(!Number.isFinite(Number(u))) throw new TypeError('legacy3d局部时间必须为有限数');
      modelFrame(index,clamp(Number(u),0,scenes[index].duration));
      return glCanvas;
    }
    function dispose(){
      world?.traverse(object=>{
        if(object.geometry) object.geometry.dispose();
        if(object.material){
          const materials=Array.isArray(object.material)?object.material:[object.material];
          materials.forEach(material=>material.dispose());
        }
      });
      renderer?.dispose();
    }
    init3D();
    if(!renderer||!renderer.getContext()) throw new Error('Three.js WebGLRenderer未能创建上下文');
    glCanvas.dataset.engine='three.js';
    const api={
      canvas:glCanvas,
      render,
      metadata:{revision:String(THREE.REVISION),source:'media/native_source/app.js#const glCanvas…function project'},
      sceneCount:scenes.length,
      size:{width:W,height:H},
      renderer,
      world,
      camera,
      getRendererInfo:()=>({revision:String(THREE.REVISION),webgl:true,geometries:renderer.info.memory.geometries,programs:renderer.info.programs?.length??null}),
      dispose
    };
    render(0,0);
    return api;
  };
})();
