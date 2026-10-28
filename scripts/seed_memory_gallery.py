"""Add long-term test examples to an isolated gallery namespace, without resetting data."""
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
USER = 'memory-gallery-demo'
BASE = 'http://127.0.0.1:8765'

def call(path, data=None, method=None):
    request=Request(BASE+path, data=json.dumps(data,ensure_ascii=False).encode() if data is not None else None, headers={'Content-Type':'application/json'},method=method)
    with urlopen(request,timeout=30) as response:
        return json.load(response)

def main():
    cases=json.loads((ROOT/'evaluation/memory-150/cases.json').read_text())['cases']
    selected={kind:[r for r in cases if r['category']==kind][:(9 if kind=='working' else 12)] for kind in ('working','episodic','semantic','procedural')}
    thread='gallery-fixture';task='sample-'+selected['working'][0]['id']
    for row in selected['working']:
        call(f'/api/architecture/working/{thread}/sample-{row["id"]}',{'user_id':USER,'patch':{'goals':[row['example']],'status':'paused'}},'PATCH')
    for kind in ('episodic','semantic'):
        for row in selected[kind]:
            candidate=({'episode_candidates':[{'observation':row['example']}]} if kind=='episodic' else {'semantic_candidates':[{'subject':USER,'predicate':'test_example_'+row['id'],'value':row['example'],'evidence_text':row['example']}]})
            response=call('/api/architecture/observe',{'observation':{'user_id':USER,'thread_id':thread,'task_id':task,'source_event_id':'gallery-'+row['id'],'content':row['example']},'analysis':candidate})
            assert all(op['status']=='succeeded' for op in response['operations']),response
    existing=call('/api/memories?user_id='+USER)['items']
    for row in selected['procedural']:
        if any(r.get('metadata',{}).get('test_case_id')==row['id'] for r in existing):continue
        result=call('/api/memories',{'user_id':USER,'content':row['example'],'memory_type':'procedural','source':'gallery_test_fixture','importance':.8,'confidence':.8,'tags':['procedure'],'metadata':{'test_case_id':row['id'],'demo':True,'executable':False,'dataset':'memory-150-v1'}})
        assert result.get('memory'),result
    rows=call('/api/memories?view=all&include_archived=true&limit=1000&user_id='+USER)['items']
    counts={kind:sum(r['memory_type']==kind for r in rows) for kind in selected}
    assert counts=={'working':9,'episodic':12,'semantic':12,'procedural':12},counts
    print(json.dumps({'namespace':USER,'total':len(rows),'by_type':counts},ensure_ascii=False))

if __name__=='__main__':main()
