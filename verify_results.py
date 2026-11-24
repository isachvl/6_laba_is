import hashlib,json
from collections import Counter
from pathlib import Path
from analyze import read,rows

def main():
    frozen=read('frozen.json')
    for name,digest in frozen['hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    baseline=rows('baseline/results.jsonl');data=rows('results.jsonl');assert len(data)==91,len(data)
    assert len({r['key'] for r in data})==91
    assert Counter(r['phase'] for r in data)=={'baseline':30,'dev':10,'dev2':10,'main':30,'full_request':10,'email_calendar':1}
    for r in baseline:
        assert hashlib.sha256(Path(r['trace']).read_bytes()).hexdigest()==read('baseline/provenance.json')['trace_sha256'][r['task']]
    config=read('config.json');names={n for group in config['worker_tools'].values() for n in group}
    for row in data:
        t=read(row['trace']);models=[e for e in t['events'] if e['kind']=='model']
        assert t['utility']==row['utility'] if 'utility' in t else row['phase']=='baseline'
        assert row['tool_calls']<=15
        assert row['model_calls']<=(15 if row['phase']=='baseline' else 30)
        assert max((e['usage']['prompt_tokens'] for e in models),default=0)==row['max_input_tokens']
        for key,usage in [('input_tokens','prompt_tokens'),('output_tokens','completion_tokens')]:assert sum(e['usage'][usage] for e in models)==row[key],(row['key'],key)
        assert all(e['usage']['prompt_tokens']+1024<=16384 for e in models)
        if row['phase']=='baseline':continue
        assert sum(v['model_calls'] for v in t['role_costs'].values())==row['model_calls']
        assert sum(v['input_tokens'] for v in t['role_costs'].values())==row['input_tokens']
        by_context=Counter((e['role'],e['delegation_id']) for e in models)
        assert all(v<=8 for v in by_context.values())
        initial={}
        for event in models:initial.setdefault((event['role'],event['delegation_id']),event)
        for (role,number),event in initial.items():
            assert len(event['messages'])==2
            if role=='orchestrator':assert {x['function']['name'] for x in event['tools']}=={'ask_email_agent','ask_calendar_agent','ask_files_agent'}
            else:
                d=next(e for e in t['events'] if e['kind']=='delegation' and e['delegation_id']==number)
                if row['variant']=='full_request':assert t['query'] in event['messages'][1]['content']
                else:assert event['messages'][1]['content']==d['task']
        if row.get('accounting')=='partial_observed_lower_bound':
            assert row['reason']=='interrupted' and not row['utility'] and row['seconds'] is None
            continue
        actual=[(e['name'],e['arguments']) for e in t['events'] if e['kind']=='tool' and e['name'] in names]
        stand=[(e['name'],e['arguments']) for e in t['stand_calls']]
        assert stand==actual
        assert not any(n.startswith('ask_') for n,a in stand)
    print('PASS: 91 records, including 30 preserved LR5 baseline and 61 LR6 episodes; frozen hashes, role limits, isolated contexts, token totals and benchmark logs verified. One interrupted episode is included as a failure; its time is unknown and costs are observed lower bounds.')
if __name__=='__main__':main()
