from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]

def main():
    narrative=json.loads((ROOT/'narration.json').read_text(encoding='utf-8'))
    weather=json.loads((ROOT/'evidence/weather.json').read_text(encoding='utf-8'))
    captions=[]
    for scene in narrative['scenes']:
        meta=json.loads((ROOT/f"audio/voice_{scene['id']}.json").read_text(encoding='utf-8'))
        offset=scene.get('speech_offset',.65)
        for i,boundary in enumerate(meta['boundaries']):
            start=scene['start']+offset+boundary['start_seconds']
            end=min(scene['end'],scene['start']+offset+boundary['end_seconds'])
            if i+1<len(meta['boundaries']):
                end=min(end,scene['start']+offset+meta['boundaries'][i+1]['start_seconds'])
            if not scene['start']<=start<end<=scene['end']:
                raise ValueError('字幕超出章节：'+scene['id'])
            captions.append({'scene':scene['id'],'start':start,'end':end,'text':boundary['text']})
    data={'timeline':narrative,'captions':captions,'evidence':{'weather':weather,'cost_scenario':{'probability':.6,'move_cost_initial':80,'move_cost_changed':600,'loss_without':1000,'loss_after':100},'project':json.loads((ROOT/'evidence/project_identity.json').read_text(encoding='utf-8'))}}
    (ROOT/'film_input.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def stamp(value):
        ms=round(value*1000)
        return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'
    (ROOT.parent/'中文字幕.srt').write_text('\n\n'.join(f"{i+1}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}" for i,c in enumerate(captions))+'\n',encoding='utf-8')
    print(json.dumps({'duration':narrative['duration'],'scenes':len(narrative['scenes']),'captions':len(captions)},ensure_ascii=False))

if __name__=='__main__':main()
