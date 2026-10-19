"""仅从通过身份校验的冻结成果提取影片数字。"""
from pathlib import Path
import hashlib,json,sys,os
import pandas as pd

ROOT=Path(__file__).resolve().parent
candidates=[Path(os.environ['MEIYU_PROJECT_ROOT'])] if os.environ.get('MEIYU_PROJECT_ROOT') else [candidate for parent in ROOT.parents for candidate in [parent,parent/'outputs/meiyu']]
PROJECT=next((p.resolve() for p in candidates if (p/'app.py').is_file() and (p/'data/samples.csv').is_file()),None)
if PROJECT is None:raise RuntimeError('未找到完整工程。请设置MEIYU_PROJECT_ROOT为含app.py及data的项目目录。')
sys.path.insert(0,str(PROJECT))
from src.bundle import load_bundle
from src.results import load_results
from src.temporal_results import load_temporal_evidence

data=load_bundle(PROJECT)
results=load_results(PROJECT,data)
temporal,errors=load_temporal_evidence(PROJECT,data.dataset_version)
assert not data.errors and results.ready and not errors
sample=data.samples.loc[data.samples.window_start_utc.eq('2025-06-01T00:00:00Z')].iloc[0]
probability=results.predictions.loc[results.predictions.sample_id.eq(sample.sample_id)&results.predictions.method.eq(results.run['selected_method']),'probability'].iloc[0]
parameters=json.loads((PROJECT/'artifacts/model_parameters.json').read_text(encoding='utf-8'))
metrics=results.evaluation['metrics']['test']
test_rows=results.predictions.loc[results.predictions.method.eq(results.run['selected_method'])&results.predictions['split'].eq('test')].merge(data.samples[['sample_id','observed_rain_mm','window_start_utc']],on='sample_id').sort_values('window_start_utc')
outcomes=[]
for row in test_rows.itertuples():
    event=row.observed_rain_mm>=25
    prepare=row.probability>=.1
    outcome=('tp' if prepare else 'fn') if event else ('fp' if prepare else 'tn')
    outcomes.append({'date':row.window_start_utc[:10],'outcome':outcome})
temporal_samples=pd.read_csv(PROJECT/'external/hangzhou_2026/data/samples.csv')
evidence={
    'dataset_version':data.dataset_version,'sample_count':len(data.samples),'sample_id':sample.sample_id,
    'probability':float(probability),'forecast_mm':float(sample.forecast_rain_mm),'reference_mm':float(sample.observed_rain_mm),
    'event_threshold_mm':results.evaluation['event_threshold_mm'],'selected_method':results.run['selected_method'],
    'splits':results.evaluation['split_summary'],'test_metrics':metrics,'logistic_rain':parameters['logistic_models']['logistic_rain'],
    'test_outcomes':outcomes,
    'temporal_observations':[{'date':row.window_start_utc[:10],'event':bool(row.observed_rain_mm>=25)} for row in temporal_samples.itertuples()],
    'temporal_counts':temporal['counts'],'monthly_coverage':temporal['monthly_coverage'],
    'inputs_sha256':{name:hashlib.sha256((PROJECT/name).read_bytes()).hexdigest() for name in ['data/samples.csv','data/source_manifest.json','artifacts/predictions.csv','artifacts/model_parameters.json','reports/evaluation.json','reports/temporal_validation.json']},
    'narration_voice':'Microsoft Huihui Desktop','original_score':'雨前的刻度',
    'scene_geometry':'示意几何，不表示真实门店、真实积水范围或数值天气空间分布'
}
assert round(evidence['probability']*100,1)==67.9 and evidence['reference_mm']==29 and evidence['forecast_mm']==52.5
(ROOT/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'passed','sample_count':len(data.samples),'probability':float(probability),'temporal_paired':temporal['counts']['paired_windows']}))
