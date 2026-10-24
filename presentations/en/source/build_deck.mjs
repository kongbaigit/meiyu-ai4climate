import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const required = name => {
  const value = process.env[name];
  if (!value) throw new Error(`Set ${name} before building.`);
  return path.resolve(value);
};
const RUNTIME_NODE_MODULES = required('RUNTIME_NODE_MODULES');
const SKILL_DIR = required('PRESENTATIONS_SKILL_DIR');
const RUNTIME_PYTHON = required('RUNTIME_PYTHON');
const workspaceDir = required('DECK_WORK_DIR');
const FINAL_PPTX = required('DECK_FINAL_PPTX');
const revision = process.env.DECK_REVISION || 'v1';
const buildDir = path.join(workspaceDir, 'build');
const previewDir = path.join(workspaceDir, 'artifact-previews');
const { Presentation, PresentationFile } = await import(pathToFileURL(
  path.join(RUNTIME_NODE_MODULES, '@oai/artifact-tool/dist/artifact_tool.mjs'),
).href);
const { finalizePresentation, applyPresentationChartFont } = await import(pathToFileURL(
  path.join(SKILL_DIR, 'container_tools/artifact_tool_utils.mjs'),
).href);

const FONT = 'Arial';
const P = {
  paper: '#F3F2E9', white: '#FFFEF8', ink: '#173E36', green: '#286C60',
  mint: '#C8E3B3', dim: '#687C6C', line: '#D6DFCF', dark: '#102E2A',
  cream: '#F0EFD7', warm: '#E8BE78', orange: '#B06945', pale: '#E4ECDC',
};
const pres = Presentation.create({slideSize:{width:1280,height:720}});
pres.theme.defaultFont = FONT;
pres.theme.colorScheme = {name:'Meiyu Prepare',themeColors:{
  accent1:P.green,accent2:P.warm,accent3:P.mint,accent4:P.orange,accent5:P.dim,accent6:P.ink,
  bg1:P.paper,bg2:P.white,tx1:P.ink,tx2:P.dim,dk1:P.dark,dk2:P.ink,lt1:P.white,lt2:P.cream,
  hlink:P.cream,folHlink:P.mint,
}};
const talks = [];
function txt(s,name,value,x,y,w,h,size=26,color=P.ink,bold=false,align='left') {
  const shape = s.shapes.add({geometry:'textbox',name,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  shape.text = value;
  shape.text.style = {typeface:FONT,fontSize:size,color,bold,alignment:align,verticalAlignment:'top',wrap:'square',autoFit:'none',insets:0};
  return shape;
}
function rule(s,name,x,y,w,fill=P.line,width=1) {
  return s.shapes.add({geometry:'line',name,position:{left:x,top:y,width:w,height:0},fill:'none',line:{style:'solid',fill,width}});
}
function arrow(s,name,x,y,w) {
  return s.shapes.add({geometry:'connector',name,kind:'straight',position:{left:x,top:y,width:w,height:0},line:{fill:P.green,width:2},tail:{type:'triangle',width:'sm',length:'sm'}});
}
function base(title,n,dark=false) {
  const s=pres.slides.add();
  s.background.fill=dark?P.dark:P.paper;
  if(title) {
    const t=txt(s,`Title ${n}`,title,72,54,1136,88,44,dark?P.cream:P.ink,true);
    t.placeholderType='title';
  }
  txt(s,`Page ${n}`,String(n).padStart(2,'0'),1166,666,42,26,18,dark?'#A9C5A9':P.dim,false,'right');
  return s;
}
function notes(s,n,title,seconds,speech,refs,qualifications=[]) {
  s.speakerNotes.text = `Suggested delivery: ${seconds} seconds\n${speech}\n\nSources\n${refs.join('\n')}\n\nDefinitions and limits\n${qualifications.join('\n')}`;
  talks.push({slide:n,title,seconds,speech,sources:refs,qualifications});
}
function table(s,name,values,x,y,w,h,widths) {
  const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:widths});
  t.name=name;
  t.styleOptions={headerRow:true,bandedRows:false,firstColumn:false,lastColumn:false};
  t.borders.assign({fill:P.line,width:1,style:'solid'});
  for(let r=0;r<values.length;r++) {
    t.rows[r].height=r===0?60:104;
    for(let c=0;c<values[0].length;c++) {
      const cell=t.getCell(r,c);
      cell.fill=r===0?P.green:P.paper;
      cell.text.style={typeface:FONT,fontSize:r===0?24:26,color:r===0?P.white:P.ink,bold:r===0,alignment:'left',verticalAlignment:'middle',insets:14};
    }
  }
  return t;
}
const repo='https://github.com/kongbaigit/meiyu-ai4climate';
const raw=file=>`${repo}/blob/main/${file}`;

{
  const s=base(null,1,true);
  txt(s,'Challenge','AI for Climate',76,59,1050,42,23,'#A9C5A9');
  txt(s,'Brand','Meiyu Prepare',70,194,1136,118,88,P.cream,true);
  txt(s,'Subtitle','Rainfall forecasts and stock relocation decisions\nfor small shops',76,341,1110,116,38,P.mint);
  txt(s,'Purpose','A working prototype for comparing expected costs',77,510,1100,51,28,P.cream);
  rule(s,'Cover rule',76,621,1128,'#36534A');
  txt(s,'Status','Built by two students. Merchant validation is pending.',77,646,1050,32,21,'#A9C5A9');
  notes(s,1,'Meiyu Prepare',15,
    'We are two students building Meiyu Prepare. Our prototype helps small shops in Hangzhou compare the expected cost of relocating stock before rain with the expected cost of keeping it in place. Merchant validation is still pending.',
    [raw('README.md'),repo],
    ['Target users and their needs remain hypotheses. The project has no completed merchant interviews.']);
}
{
  const s=base('The small shop dilemma',2);
  txt(s,'Audience','Target users: small shops in Hangzhou preparing for wet weather',76,157,1120,54,29,P.green);
  txt(s,'Relocate heading','Relocate now',76,272,510,72,52,P.ink,true);
  txt(s,'Keep heading','Keep stock in place',728,272,480,72,45,P.ink,true);
  rule(s,'Relocate rule',76,367,468,P.green,3);
  rule(s,'Keep rule',730,367,467,P.orange,3);
  txt(s,'Relocate cost','Pay for labour and materials.\nReduce stock loss if an event occurs.',76,404,504,112,28,P.ink);
  txt(s,'Keep cost','Avoid the immediate relocation cost.\nLeave the stock exposed.',730,404,476,112,28,P.ink);
  txt(s,'Decision scope','Weather is uncertain. Preparation has a cost.\nThe prototype makes the assumptions and calculation visible.',76,563,1120,81,27,P.dim);
  notes(s,2,'The small shop dilemma',17,
    'Relocation takes labour and materials. Keeping stock in place avoids that immediate expense but leaves exposure. We focus on this specific choice. The need is a hypothesis, so the prototype first makes its inputs and assumptions visible.',
    [raw('docs/decision-guide.md'),raw('docs/90%E5%A4%A9%E9%AA%8C%E8%AF%81%E8%AE%A1%E5%88%92.md')],
    ['No completed merchant recruitment or needs validation supports the target-user statement.']);
}
{
  const s=base('A single 24-hour decision',3);
  txt(s,'Workflow summary','Choose a weather window, then enter your own cost assumptions',76,156,1120,53,29,P.green);
  const xs=[76,483,891];
  const headings=['Weather window','Cost assumptions','Cost comparison'];
  const bodies=['Location and 24-hour window\nCapture time\nData completeness','Relocation cost C\nEvent loss if kept L₀\nEvent loss after relocation L₁','Expected cost comparison\nSources and assumptions'];
  xs.forEach((x,i)=>{
    txt(s,`Step number ${i+1}`,`0${i+1}`,x,258,250,58,44,P.green,true);
    txt(s,`Step heading ${i+1}`,headings[i],x,336,310,58,32,P.ink,true);
    rule(s,`Step rule ${i+1}`,x,408,304,P.line,2);
    txt(s,`Step detail ${i+1}`,bodies[i],x,438,305,135,23.5,P.ink);
  });
  arrow(s,'Workflow connector 1',398,365,68);
  arrow(s,'Workflow connector 2',805,365,69);
  txt(s,'Completeness boundary','Missing members, missing hours or stale data stop the weather calculation.',76,609,1120,54,25,P.dim);
  notes(s,3,'A single 24-hour decision',17,
    'Users choose a location and a 24-hour window, then enter relocation cost and conditional losses for both options. The page compares expected total costs and retains the sources. Missing members, missing hours or stale weather data stop the weather calculation.',
    [raw('README.md'),raw('docs/decision-guide.md')],
    ['The workflow describes implemented prototype behaviour, not observed merchant usage.']);
}
{
  const s=base('A paired dataset with 24-hour windows',4);
  txt(s,'Historical data sources','Fixed-lead ECMWF forecasts paired with Xiaoshan Airport SSOD reference data',76,155,1120,54,27,P.green);
  table(s,'Paired historical example',[
    ['Window (UTC+08)','Forecast (mm)','Reference (mm)','Quality'],
    ['2025-06-01 08:00\nto 2025-06-02 08:00','52.5','29.0','passed'],
  ],76,239,1130,164,[415,255,255,205]);
  const xs=[77,479,881],numbers=['731','670','636'],labels=['Calendar days','Complete reference days','Complete paired days'];
  xs.forEach((x,i)=>{
    txt(s,`Coverage value ${i+1}`,numbers[i],x,451,285,82,62,i===2?P.green:P.ink,true);
    txt(s,`Coverage label ${i+1}`,labels[i],x,538,305,57,24,P.dim);
  });
  txt(s,'Exclusion rule','Exclude windows with a required hour missing, invalid data or negative rain.\nNever fill missing observations with zero.',77,611,1115,64,23,P.ink);
  notes(s,4,'Paired historical data',20,
    'Each row pairs a forecast and reference rainfall over the same 24 hours. The configured calendar has 731 days across 2024 and 2025. There are 670 complete reference days and 636 complete pairs. We exclude incomplete windows rather than treating missing observations as zero rain.',
    [raw('data/samples.csv'),raw('docs/data_dictionary.md'),'https://open-meteo.com/en/docs','https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly/synoptic-summary-of-the-day'],
    ['08:00 to the next 08:00 in UTC+08 corresponds to a nominal UTC day.','The quality flag passed means the row passed project rules. It does not imply independent validation of the rainfall value.','The English deck retains the fixed example from the Chinese source deck dated 19 October 2026.']);
}
{
  const s=base('Historical model and online ensemble',5);
  txt(s,'Historical lane','Historical offline study',76,146,540,44,30,P.green,true);
  txt(s,'Online lane','Archived online snapshot',681,146,525,44,30,P.green,true);
  rule(s,'Historical lane rule',76,195,526,P.green,4);
  rule(s,'Online lane rule',681,195,525,P.green,4);
  txt(s,'Historical input','52.5 mm',76,225,520,64,48,P.ink,true);
  txt(s,'Historical date','Forecast for 1 Jun 2025',77,296,520,38,22,P.dim);
  txt(s,'Historical transformation','log1p and standardization\nLogistic regression',77,351,525,89,28,P.ink);
  txt(s,'Historical output','67.9%',75,455,400,79,60,P.green,true);
  txt(s,'Historical meaning','P(reference daily rainfall ≥ 25 mm)',77,539,530,40,23,P.ink);
  txt(s,'Historical splits','Train 276 days, validation 120 days\nTest 240 days with 18 events',77,595,530,58,21,P.dim);
  txt(s,'Online dimensions','51 members × 24 hours',680,227,525,62,38,P.ink,true);
  txt(s,'Online window','20 Oct 08:00 to 21 Oct 08:00 (UTC+08)',681,296,525,40,21,P.dim);
  txt(s,'Online aggregation','Sum rain for each member\nCount totals at or above 25 mm',681,351,525,89,27,P.ink);
  txt(s,'Online fraction','0 / 51 = 0%',679,455,528,79,54,P.green,true);
  txt(s,'Online meaning','Uncalibrated ensemble member fraction',681,539,525,43,22,P.ink);
  txt(s,'Online capture','Captured 19 Oct 2026, 19:22 (UTC+08)',681,598,525,48,20,P.dim);
  txt(s,'Probability limits','Neither output represents a shop flood or stock loss probability. The historical model serves offline research only.',77,657,1080,35,18.5,P.orange);
  notes(s,5,'Historical model and online ensemble',24,
    'The historical model and online ensemble have different meanings. The offline example converts 52.5 millimetres into a 67.9 percent probability of the reference rainfall event. The archived online snapshot counts zero of 51 members reaching 25 millimetres. That member fraction lacks local calibration. Neither output is a shop flood or stock loss probability.',
    [raw('artifacts/model_parameters.json'),raw('artifacts/predictions.csv'),raw('reports/evaluation.json'),raw('src/decision_weather.py')],
    ['Historical model: logistic_rain, trained on 276 days, selected on 120 validation days and evaluated on 240 test days with 18 events.','The example uses forecast rainfall as its input. Reference rainfall is a later evaluation label.','Fixed snapshot captured 2026-10-19 19:22 UTC+08 for 2026-10-20 08:00 through 2026-10-21 08:00 UTC+08. It is not current weather.','Online source: Open-Meteo ECMWF IFS 0.25 degree ensemble, 51 members and 24 required hourly values per member.','Source snapshot SHA-256: 2c91ea4481afc3ee2d53bbbe863ec4ed8723a693219ca12b8b1bb319090d1a6c']);
}
{
  const s=base('A CNY 460 gap in expected cost',6,true);
  txt(s,'Scenario status','Hypothetical inputs, separate from weather forecasts',76,153,1110,48,29,P.mint);
  txt(s,'Conditional losses','Event losses: L₀ = CNY 1,000 if kept, L₁ = CNY 100 after relocation',76,216,1110,44,25,P.cream);
  txt(s,'Relocation inputs','Relocation cost C = CNY 80 (labour 60 + materials 20)',76,270,1110,44,25,P.cream);
  txt(s,'Hypothetical probability','Assumed event probability p = 60%',76,319,1110,40,25,P.cream);
  rule(s,'Cost comparison rule',76,375,1127,'#36534A');
  txt(s,'Keep option','Keep stock in place',76,408,540,52,32,P.cream,true);
  txt(s,'Keep formula','pL₀ = 0.60 × 1,000',76,474,520,44,28,'#A9C5A9');
  txt(s,'Keep expected cost','CNY 600',73,525,530,87,64,P.cream,true);
  txt(s,'Relocate option','Relocate',729,408,450,52,32,P.mint,true);
  txt(s,'Relocate formula','C + pL₁ = 80 + 0.60 × 100',729,474,480,44,27,'#A9C5A9');
  txt(s,'Relocate expected cost','CNY 140',726,525,478,87,64,P.mint,true);
  rule(s,'Cost result rule',76,632,1127,'#36534A');
  txt(s,'Expected cost qualification','The CNY 460 difference comes from this scenario. Actual merchant loss reduction is unverified.',77,651,1080,37,21,P.cream);
  notes(s,6,'Expected cost example',21,
    'Now consider a hypothetical decision, separate from weather forecasts. Assume a 60 percent event probability, a 1,000-yuan loss if stock stays, a 100-yuan residual loss after relocation, and an 80-yuan relocation cost. Expected costs are 600 and 140 yuan. The 460-yuan difference is a calculation, with no verified merchant savings.',
    [raw('docs/decision-guide.md')],
    ['Hypothetical inputs: p=0.6, C=80, L0=1000, L1=100, all money in CNY.','Keep expected cost = pL0. Relocate expected cost = C+pL1. This example assumes no stock loss when the event does not occur.','C=60 labour + 20 materials is an illustrative decomposition.','The 60% scenario input does not come from the online ensemble or the historical model.']);
}
{
  const s=base('Relocation cost changes the choice',7);
  txt(s,'Sensitivity assumptions','Same assumptions: p = 60%, L₀ = CNY 1,000, L₁ = CNY 100',76,154,1120,45,27,P.green);
  const chart=s.charts.add('scatter',{
    position:{left:61,top:224,width:795,height:389},
    hasLegend:true,legend:{position:'bottom',overlay:false,textStyle:{fontSize:22,fill:P.ink}},
    scatterOptions:{style:'lineWithMarkers'},
    series:[
      {name:'Keep in place',xValues:[0,80,200,400,540,600],values:[600,600,600,600,600,600],line:{fill:P.dim,width:3},marker:{symbol:'none',size:2,fill:P.dim}},
      {name:'Relocate',xValues:[0,80,200,400,540,600],values:[60,140,260,460,600,660],line:{fill:P.green,width:4},marker:{symbol:'circle',size:5,fill:P.green}},
    ],
    xAxis:{title:'Relocation cost C (CNY)',min:0,max:600,majorUnit:200,numberFormatCode:'0',textStyle:{fontSize:20,fill:P.dim},line:{fill:P.line,width:1},majorGridlines:null},
    yAxis:{title:'Expected total cost (CNY)',min:0,max:700,majorUnit:200,numberFormatCode:'0',textStyle:{fontSize:20,fill:P.dim},line:{fill:'none',width:0},majorGridlines:{fill:P.line,width:1}},
    chartFill:P.paper,plotAreaFill:P.paper,chartLine:{fill:'none',width:0},plotAreaLine:{fill:'none',width:0},
  });
  applyPresentationChartFont(chart,{fontFamily:FONT});
  txt(s,'Cost 80','C = CNY 80',907,234,296,43,28,P.green,true);
  txt(s,'Cost 80 decision','Relocate: CNY 140\nKeep: CNY 600',907,288,296,83,24,P.ink);
  rule(s,'Sensitivity divider',907,389,295,P.line);
  txt(s,'Cost 540 tie','C = CNY 540\nEqual expected costs',907,412,296,81,27,P.ink,true);
  txt(s,'Cost 600 keep','C = CNY 600\nKeep stock in place',907,530,296,79,27,P.orange,true);
  txt(s,'Break even equation','Break-even cost C* = p(L₀ − L₁) = CNY 540. Inputs determine the comparison.',77,639,1110,43,23,P.dim);
  notes(s,7,'Relocation cost sensitivity',17,
    'Changing relocation cost changes the choice. At 80 yuan, relocation has the lower expected cost. At 540 yuan, the options tie. At 600 yuan, relocation costs 660 yuan in expectation, so keeping stock has the lower expected cost.',
    [raw('docs/decision-guide.md')],
    ['The native scatter chart retains the actual numeric distance between costs.','Keep total cost remains 600. Relocate total cost equals C+60. Break-even cost = p(L0-L1) = 0.6(1000-100) = 540.','These are hypothetical scenario calculations, not observed merchant outcomes.']);
}
{
  const s=base('Evidence and limits',8);
  txt(s,'Test scope','Offline study: the same 240 test days with 18 reference events',76,154,1120,44,27,P.green);
  txt(s,'Chart heading','Test Brier score (lower is better)',77,226,650,44,26,P.ink,true);
  const chart=s.charts.add('bar',{
    position:{left:65,top:291,width:660,height:273},categories:['logistic_rain','climatology'],
    series:[{name:'Test Brier',values:[0.0455,0.0697],fill:P.green,points:[{idx:0,fill:P.green},{idx:1,fill:'#94AC8A'}]}],
    hasLegend:false,barOptions:{direction:'bar',grouping:'clustered',gapWidth:110},
    dataLabels:{showValue:true,position:'outEnd',numberFormatCode:'0.0000',textStyle:{fontSize:24,fill:P.ink}},
    xAxis:{min:0,max:0.085,majorUnit:0.02,numberFormatCode:'0.00',textStyle:{fontSize:18,fill:P.dim},line:{fill:P.line,width:1},majorGridlines:{fill:P.line,width:1}},
    yAxis:{textStyle:{fontSize:22,fill:P.ink},line:{fill:'none',width:0},majorGridlines:null},
    chartFill:P.paper,plotAreaFill:P.paper,chartLine:{fill:'none',width:0},plotAreaLine:{fill:'none',width:0},
  });
  applyPresentationChartFont(chart,{fontFamily:FONT});
  txt(s,'Baseline definition','Climatology uses the training event rate.',77,574,650,38,22,P.dim);
  txt(s,'Test sample limit','Only 18 test events\nReference labels have limits',790,230,420,87,28,P.ink,true);
  txt(s,'Calibration limit','Online fraction still needs\nlocal calibration',790,351,420,86,28,P.ink,true);
  txt(s,'Outcome evidence limit','Merchant loss reduction and\ncarbon benefits are unverified',790,472,420,88,28,P.ink,true);
  txt(s,'Threshold errors','At a fixed 10% scenario threshold: 6 missed events and 9 false alarms.\nLow probability still carries risk.',77,623,1110,59,23,P.orange);
  notes(s,8,'Evidence and limits',20,
    'On the held-out test set, logistic rain scores 0.0455 on Brier, compared with 0.0697 for climatology. Lower is better. Yet there are only 18 test events. At a fixed 10 percent scenario threshold, the model misses six events and raises nine false alarms. Merchant and carbon benefits remain unverified.',
    [raw('reports/evaluation.json'),raw('artifacts/sample_splits.csv'),raw('artifacts/predictions.csv')],
    ['Both Brier scores refer to the same test split. Climatology is the constant event rate estimated on training data.','Model selection used validation data. The test period remained separate.','The 6 missed events and 9 false alarms use a fixed 10% scenario threshold. This is not an equal-false-alarm comparison.','The project has no verified merchant loss reduction, deployment outcomes or carbon benefit measurements.']);
}
{
  const s=base('A 90-day validation plan',9);
  txt(s,'Plan status','Pending plan by two students. Recruitment has not started.',76,154,1120,44,28,P.green);
  const xs=[77,370,664,958],width=245;
  const periods=['Weeks 1 to 2','Weeks 3 to 4','Weeks 5 to 8','Weeks 9 to 12'];
  const headings=['Needs check','Understanding','Shadow run','Review'];
  const details=['Recruit 5 to 8\nwilling participants','Fixed historical cases\nLog misconceptions','Check forecast access\nLog failures and gaps','Review tasks and failures\nContinue, revise or stop'];
  xs.forEach((x,i)=>{
    txt(s,`Plan period ${i+1}`,periods[i],x,254,width,45,25,P.green,true);
    txt(s,`Plan heading ${i+1}`,headings[i],x,329,width,55,i===1?29:31,P.ink,true);
    rule(s,`Plan rule ${i+1}`,x,400,width,P.line,2);
    txt(s,`Plan detail ${i+1}`,details[i],x,432,width,111,22.5,P.ink);
  });
  for(let i=0;i<3;i++)arrow(s,`Plan connector ${i+1}`,xs[i]+width+12,355,xs[i+1]-(xs[i]+width)-24);
  txt(s,'Planned target','Planned target: at least 80% complete the task within 3 minutes\nand explain the key limits correctly.',77,565,1125,66,24,P.ink);
  txt(s,'Plan limitation','Small-sample usability study. This 90-day period does not cover the next full Meiyu season.',77,641,1110,40,22,P.orange);
  notes(s,9,'The 90-day plan',19,
    'Our pending 90-day plan starts with five to eight willing participants. Fixed historical cases will test understanding, followed by shadow operation and failure logging. We will assess task completion and understanding separately. This is a small usability study. A fresh full Meiyu season is still needed for independent predictive evidence.',
    [raw('docs/90%E5%A4%A9%E9%AA%8C%E8%AF%81%E8%AE%A1%E5%88%92.md'),raw('docs/%E7%94%A8%E6%88%B7%E6%B5%8B%E8%AF%95%E6%89%A7%E8%A1%8C%E5%8C%85/')],
    ['The plan has not been executed and participants have not been recruited.','Day 1 begins when the team confirms the start date. Weeks describe phases within the 90-day period.','The 80% target is preregistered for a future study, not an observed result. Independent completion and core understanding are scored separately.','The planned 90 days do not include the next complete Meiyu rainfall season.']);
}
{
  const s=base(null,10,true);
  txt(s,'Closing brand','Meiyu Prepare',73,76,1100,100,76,P.cream,true);
  txt(s,'Next evidence','Next: test whether merchants can complete\nand understand the comparison',77,218,1105,107,37,P.mint);
  rule(s,'Closing rule',77,370,1125,'#36534A');
  const links=[
    ['English demo','kongbaigit.github.io/meiyu-ai4climate/en/','https://kongbaigit.github.io/meiyu-ai4climate/en/'],
    ['English video','kongbaigit.github.io/meiyu-ai4climate/en/promo/','https://kongbaigit.github.io/meiyu-ai4climate/en/promo/'],
    ['Code and evidence','github.com/kongbaigit/meiyu-ai4climate',repo],
  ];
  links.forEach((item,i)=>{
    const y=398+i*89;
    txt(s,`Link label ${i+1}`,item[0],78,y,1100,27,20,'#A9C5A9');
    const link=txt(s,`Link ${i+1}`,item[1],78,y+31,1120,43,28,P.cream);
    link.text.get(item[1]).link={uri:item[2],isExternal:true};
  });
  notes(s,10,'English demo and source',10,
    'The English demo, video and source links are here. Please inspect the calculation and its limits. Our next priority is real user understanding. Thank you.',
    ['https://kongbaigit.github.io/meiyu-ai4climate/en/','https://kongbaigit.github.io/meiyu-ai4climate/en/promo/',repo],
    ['The links identify the English release destinations. The deck makes no claim that the merchant study has begun.']);
}

await fs.mkdir(buildDir,{recursive:true});
await fs.mkdir(previewDir,{recursive:true});
await fs.mkdir(path.dirname(FINAL_PPTX),{recursive:true});
await fs.writeFile(path.join(buildDir,`deck-${revision}.proto.json`),JSON.stringify(pres.toProto()));
await fs.writeFile(path.join(buildDir,`speech-${revision}.json`),JSON.stringify({totalSeconds:talks.reduce((a,b)=>a+b.seconds,0),talks},null,2));
for(const [i,s] of pres.slides.items.entries()) {
  const layout=await s.export({format:'layout'});
  await fs.writeFile(path.join(previewDir,`slide-${String(i+1).padStart(2,'0')}.layout.json`),await layout.text());
}
const candidatePath=path.join(buildDir,`candidate-${revision}.pptx`);
await (await PresentationFile.exportPptx(pres)).save(candidatePath);
const requirements={
  explicitTotalSlideCount:10,
  requiredNativeTableOwnerSlides:[4],
  requiredNativeChartOwnerSlides:[7,8],
  materializeLiteralChartWorkbooks:true,
};
const result=await finalizePresentation({
  ...requirements,workspaceDir,candidatePath,finalPath:FINAL_PPTX,pythonExecutable:RUNTIME_PYTHON,
  integrityValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','4'],
  fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,
  receiptPath:path.join(buildDir,`${revision}.validation.json`),
});
await fs.writeFile(path.join(buildDir,`${revision}.finalizer-result.json`),JSON.stringify(result,null,2));
const wordCount=talks.reduce((sum,t)=>sum+(t.speech.match(/\b[\w]+(?:['-][\w]+)*\b/g)||[]).length,0);
const md=[
  '# Meiyu Prepare: three-minute speaker notes',
  '',
  `Suggested delivery: 180 seconds across 10 slides. Speech length: ${wordCount} words.`,
  '',
  'The spoken script appears first for each slide. Source and definition notes are for reference.',
  '',
  ...talks.flatMap(t=>[
    `## ${String(t.slide).padStart(2,'0')}. ${t.title} (${t.seconds} seconds)`,
    '',t.speech,'',
    'Sources:','',...t.sources.map(s=>`- ${s}`),'',
    'Definitions and limits:','',...t.qualifications.map(q=>`- ${q}`),'',
  ]),
  '## Formula reference',
  '',
  'All example amounts use CNY. The example assumes no stock loss when the event does not occur.',
  '',
  '$$E_{\\mathrm{keep}}=pL_0=0.6\\times1000=600$$',
  '',
  '$$E_{\\mathrm{relocate}}=C+pL_1=80+0.6\\times100=140$$',
  '',
  '$$E_{\\mathrm{keep}}-E_{\\mathrm{relocate}}=460$$',
  '',
  '$$C^*=p(L_0-L_1)=0.6(1000-100)=540$$',
  '',
].join('\n');
await fs.writeFile(path.join(path.dirname(FINAL_PPTX),'speaker-notes.md'),md);
console.log(JSON.stringify({finalPath:FINAL_PPTX,slides:10,seconds:180,speechWords:wordCount,validationResult:result}));
