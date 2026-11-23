import argparse,hashlib,json,time,sys
from pathlib import Path
from agentdojo.task_suite.load_suites import get_suites
from base_agent import Agent as SingleAgent
from multi_agent import MultiAgent

ROOT=Path(__file__).resolve().parent

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')

def run(phase,architecture='multi'):
    config=read('config.json' if architecture=='multi' else 'config_single.json')
    manifest=read('reference/lr5_manifest.json')
    variant={'dev':'multi','dev2':'multi','main':'multi','full_request':'full_request','email_calendar':'email_calendar'}[phase]
    if phase not in ('dev','dev2'):
        for name,digest in read('frozen.json')['hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    if phase in ('dev','dev2'):ids=manifest['ids']['workspace_dev']
    elif phase=='main':ids=manifest['ids']['workspace_main']
    elif phase=='full_request':ids=read('selection.json')['tasks']
    else:ids=['user_task_15']
    output=Path('results')/(phase+('_single' if architecture=='single' else '')+'.jsonl');output.parent.mkdir(exist_ok=True)
    complete={r['key'] for r in map(json.loads,output.read_text(encoding='utf-8').splitlines())} if output.exists() else set()
    suite=get_suites(config['benchmark'])['workspace']
    for index,task in enumerate(ids,1):
        key=f'workspace__{task}__{phase}__{architecture}__r0__s42'
        if key in complete:continue
        path=Path('traces')/(key+'.json')
        if path.exists():raise RuntimeError('Partial episode requires review: '+key)
        agent=MultiAgent(config,path,variant) if architecture=='multi' else SingleAgent(config,'react',path)
        agent.trace.update(key=key,phase=phase,task=task,architecture=architecture,seed=42,temperature=0)
        agent.save();start=time.perf_counter();error=None
        try:utility,_=suite.run_task_with_pipeline(agent,suite.get_user_task_by_id(task),None,{})
        except Exception as exc:
            utility=False;error=repr(exc);agent.trace.update(reason='evaluation_error',evaluation_error=error)
        finally:agent.client.close();agent.http.close()
        events=[e for e in agent.trace['events'] if e['kind']=='model']
        peaks=[e['usage']['prompt_tokens'] for e in events]
        agent.trace.update(utility=bool(utility));agent.save()
        row={'key':key,'suite':'workspace','task':task,'phase':phase,'architecture':architecture,'variant':variant if architecture=='multi' else 'single',
             'python_executable':sys.executable,'utility':bool(utility),'reason':agent.trace['reason'],'answer':agent.trace.get('answer',''),
             **{k:agent.trace[k] for k in ['model_calls','tool_calls','input_tokens','output_tokens']},
             'max_input_tokens':max(peaks,default=0),'seconds':agent.trace.get('seconds',time.perf_counter()-start),
             'role_costs':agent.trace.get('role_costs',{}),'delegations':agent.trace.get('delegations',0),'trace':str(path),'evaluation_error':error}
        with output.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
        print(index,len(ids),key,utility,row['reason'],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['dev','dev2','main','full_request','email_calendar']);p.add_argument('--architecture',choices=['single','multi'],default='multi');a=p.parse_args();run(a.phase,a.architecture)
