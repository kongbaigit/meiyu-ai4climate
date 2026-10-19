function txt(value,x,y,size=30,color=P.ink,weight=400,align='left',alpha=1,font=FACE) {
  ctx.save();ctx.globalAlpha*=clamp(alpha);ctx.fillStyle=color;ctx.font=weight+' '+size+'px '+font;ctx.textBaseline='alphabetic';ctx.textAlign=align;
  const v=String(value),width=ctx.measureText(v).width;
  ctx.fillText(v,x,y);
  if(ctx.globalAlpha>.06) bounds.push({text:v,x:align==='right'?x-width:align==='center'?x-width/2:x,y:y-size,width,height:size*1.25});
  ctx.restore();
}
function words(value,x,y,width,size=28,color=P.dim,lh=44,weight=400) {
  ctx.font=weight+' '+size+'px '+FACE;
  let line='',row=0;
  for(const ch of value){
    if(ch==='\n'||(line&&ctx.measureText(line+ch).width>width)){
      txt(line,x,y+lh*row,size,color,weight);line=ch==='\n'?'':ch;row++;
    }else line+=ch;
  }
  if(line)txt(line,x,y+lh*row,size,color,weight);
  return (row+1)*lh;
}
function rr(x,y,w,h,r,fill,stroke=null,lw=1){
  ctx.beginPath();ctx.roundRect(x,y,w,h,r);if(fill){ctx.fillStyle=fill;ctx.fill();}
  if(stroke){ctx.lineWidth=lw;ctx.strokeStyle=stroke;ctx.stroke();}
}
function line(x1,y1,x2,y2,color=P.line,width=1,alpha=1){
  ctx.save();ctx.globalAlpha*=alpha;ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke();ctx.restore();
}
function dot(x,y,r,color){ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();}
function pill(text,x,y,fill=P.mint,color=P.ink,size=22){
  ctx.font='500 '+size+'px '+FACE;const w=ctx.measureText(text).width+34;rr(x,y-30,w,45,23,fill);txt(text,x+17,y,size,color,500);return w;
}
function logo(x,y,size=36,color=P.green){
  ctx.save();ctx.translate(x,y);ctx.scale(size/40,size/40);ctx.beginPath();ctx.moveTo(0,-23);ctx.bezierCurveTo(-8,-11,-20,0,-20,10);ctx.bezierCurveTo(-20,32,20,32,20,10);ctx.bezierCurveTo(20,0,8,-11,0,-23);ctx.fillStyle=color;ctx.fill();ctx.lineWidth=6;ctx.lineCap='round';ctx.strokeStyle=color===P.green?P.cream:P.dark;ctx.beginPath();ctx.moveTo(-8,10);ctx.lineTo(8,10);ctx.stroke();ctx.restore();
}
function pointer(x,y,t,clickedAt=-100,color=P.white){
  const d=t-clickedAt;
  if(d>=0&&d<.65){ctx.save();ctx.globalAlpha=(1-d/.65)*.55;ctx.strokeStyle=P.green;ctx.lineWidth=3;ctx.beginPath();ctx.arc(x,y,15+d*50,0,Math.PI*2);ctx.stroke();ctx.restore();}
  ctx.save();ctx.translate(x,y);ctx.shadowColor='#0a211a35';ctx.shadowBlur=10;ctx.shadowOffsetY=4;
  ctx.beginPath();ctx.moveTo(0,0);ctx.lineTo(4,35);ctx.lineTo(13,26);ctx.lineTo(23,43);ctx.lineTo(30,39);ctx.lineTo(20,23);ctx.lineTo(33,20);ctx.closePath();ctx.fillStyle=color;ctx.fill();ctx.shadowBlur=0;ctx.shadowOffsetY=0;ctx.lineWidth=2;ctx.strokeStyle=P.ink;ctx.stroke();ctx.restore();
}
function arrow(x1,y1,x2,y2,color=P.green,w=3){
  line(x1,y1,x2,y2,color,w);const a=Math.atan2(y2-y1,x2-x1);line(x2,y2,x2-13*Math.cos(a-.5),y2-13*Math.sin(a-.5),color,w);line(x2,y2,x2-13*Math.cos(a+.5),y2-13*Math.sin(a+.5),color,w);
}
function polygon(points,fill,stroke=null){
  ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();ctx.fillStyle=fill;ctx.fill();if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=1.4;ctx.stroke();}
}
function shop(t) {
  const ox=1424,oy=692,iso=(x,z,y=0)=>[ox+(x-z)*.72,oy+(x+z)*.35-y];
  function cube(x,z,y,w,d,h,top,front,side){
    const a=iso(x,z,y),b=iso(x+w,z,y),c=iso(x+w,z+d,y),e=iso(x,z+d,y);
    const aa=iso(x,z,y+h),bb=iso(x+w,z,y+h),cc=iso(x+w,z+d,y+h),ee=iso(x,z+d,y+h);
    polygon([e,c,cc,ee],front,'#83aa8a30');polygon([b,c,cc,bb],side,'#83aa8a30');polygon([aa,bb,cc,ee],top,'#91b69b50');
  }
  cube(-260,-200,-16,540,400,16,'#365548','#29463c','#203c34');
  for(let k=-2;k<=2;k++){const a=iso(k*90,-200,1),b=iso(k*90,200,1);line(...a,...b,'#91b69b',1,.13);}
  cube(-240,-170,0,480,16,244,'#8ba78c','#304c41','#29463c');
  cube(-240,-170,0,12,300,244,'#7c9c7f','#38584a','#304c41');
  cube(-260,-180,244,530,305,13,'#c4d8af','#6d9374','#4e765f');
  for(let j=0;j<7;j++)cube(-255+j*76,103,222,74,21,22,j%2?'#c5d8b2':'#8ab596',j%2?'#a0bc94':'#659272','#5b7d62');
  const points=[[-170,-60,0],[-70,-60,0],[30,-60,0],[-170,38,0],[-68,40,0],[32,40,0],[-170,-60,72],[-68,-60,72],[32,-60,72]];
  points.forEach((p,j)=>{
    const lift=phase(4+j*.12,6.3+j*.12,t)*17;
    cube(p[0],p[1],p[2]+lift,78,72,64,j%3?'#e5dfbb':'#d8b886',j%3?'#aebc95':'#b99a69',j%3?'#839d79':'#957a50');
    const a=iso(p[0]+35,p[1]+74,p[2]+lift+18),b=iso(p[0]+51,p[1]+74,p[2]+lift+18);
    line(...a,...b,'#4e7258',3);
  });
  for(let k=0;k<96;k++){
    const x=1040+seed(k)*755,y=236+(seed(k,1)*560+t*(115+seed(k,2)*80))%560;
    const len=8+seed(k,3)*12;line(x,y,x-3,y+len,'#b9d3ad',1.2,.16);
  }
  txt('场景示意',1705,824,21,'#9bb298',400,'right');
}
