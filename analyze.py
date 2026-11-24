import csv,hashlib,json,statistics
from pathlib import Path

MULTI_IDS=['user_task_'+str(i) for i in [13,15,18,19,23,25,33]]
KEYS=['model_calls','tool_calls','input_tokens','output_tokens','seconds']

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def rows(p):return [json.loads(l) for l in Path(p).read_text(encoding='utf-8').splitlines()]
def save(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def csv_file(path,data):
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)

def stats(data,key):
    values=[r[key] for r in data if r[key] is not None]
    return {'n_observed':len(values),'median':statistics.median(values),'min':min(values),'max':max(values),'total':sum(values)}

def compare(a,b,ids):
    first={r['task']:r for r in a};second={r['task']:r for r in b}
    return {'n':len(ids),'single_success':sum(first[i]['utility'] for i in ids),'multi_success':sum(second[i]['utility'] for i in ids),
            'gained':[i for i in ids if not first[i]['utility'] and second[i]['utility']],
            'lost':[i for i in ids if first[i]['utility'] and not second[i]['utility']],
            'both_success':[i for i in ids if first[i]['utility'] and second[i]['utility']],
            'both_failure':[i for i in ids if not first[i]['utility'] and not second[i]['utility']]}

def handoffs(row):
    trace=read(row['trace']);returns={e['delegation_id']:e for e in trace['events'] if e['kind']=='worker_return'}
    result=[]
    for event in trace['events']:
        if event['kind']!='delegation':continue
        number=event['delegation_id'];done=returns.get(number,{})
        result.append({'id':number,'role':event['role'],'task':event['task'],'answer':done.get('answer','No worker return; episode stopped.'),
                       'reason':done.get('reason',trace['reason']),
                       'tools':[{k:e.get(k) for k in ['name','arguments','output','error','executed']} for e in trace['events'] if e['kind']=='tool' and e['delegation_id']==number]})
    return result

def select():
    main=rows('results/main.jsonl');assert len(main)==30
    singles=[r for r in main if r['task'] not in MULTI_IDS]
    chosen=sorted(singles,key=lambda r:(r['utility'],-r['input_tokens'],r['task']))[:3]
    value={'rule':'All 7 multi-service tasks, plus 3 single-service tasks: failures first, then descending episode input tokens; ties by task ID.',
           'source_sha256':hashlib.sha256(Path('results/main.jsonl').read_bytes()).hexdigest(),
           'tasks':MULTI_IDS+[r['task'] for r in chosen],
           'selected_single':[{'task':r['task'],'utility':r['utility'],'input_tokens':r['input_tokens']} for r in chosen]}
    save('selection.json',value);print('Selected:',value['tasks'])

def analyze():
    base=rows('baseline/results.jsonl');main=rows('results/main.jsonl');full=rows('results/full_request.jsonl');expanded=rows('results/email_calendar.jsonl')
    assert len(base)==len(main)==30 and len(full)==10 and len(expanded)==1
    all_rows=base+[r for p in sorted(Path('results').glob('*.jsonl')) for r in rows(p)]
    assert len({r['key'] for r in all_rows})==len(all_rows)
    Path('results.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in all_rows),encoding='utf-8')
    ids=[r['task'] for r in base];singles=[i for i in ids if i not in MULTI_IDS]
    groups={name:compare(base,main,items) for name,items in [('all',ids),('multi_service',MULTI_IDS),('single_service',singles)]}
    costs={name:{key:stats(data,key) for key in KEYS} for name,data in [('single',base),('multi',main)]}
    ratios={key:costs['multi'][key]['median']/costs['single'][key]['median'] for key in KEYS}
    context={name:stats(data,'max_input_tokens') for name,data in [('single',base),('multi',main)]}
    role_costs={}
    for role in ['orchestrator','email','calendar','files']:
        role_costs[role]={k:sum(r['role_costs'].get(role,{}).get(k,0) for r in main) for k in ['model_calls','input_tokens','output_tokens','model_seconds']}
    selection=read('selection.json')['tasks'];selected=[r for r in main if r['task'] in selection]
    second={'pairs':compare(selected,full,selection),'costs':{name:{k:stats(data,k) for k in KEYS} for name,data in [('subtask',selected),('full_request',full)]},
            'context':{name:stats(data,'max_input_tokens') for name,data in [('subtask',selected),('full_request',full)]}}
    ms_fail=[r for r in main if r['task'] in MULTI_IDS and not r['utility']]
    ss_fail=sorted([r for r in main if r['task'] not in MULTI_IDS and not r['utility']],key=lambda r:-r['input_tokens'])[:2]
    if len(ss_fail)<2:ss_fail+=sorted([r for r in main if r['task'] not in MULTI_IDS and r['utility']],key=lambda r:-r['input_tokens'])[:2-len(ss_fail)]
    cases=[{'task':r['task'],'utility':r['utility'],'trace':r['trace'],'query':read(r['trace'])['query'],'answer':r['answer'],'handoffs':handoffs(r)} for r in ms_fail+ss_fail]
    save('analysis/case_candidates.json',cases)
    save('analysis/experiment2_candidates.json',[{'task':i,'subtask':{'row':next(r for r in selected if r['task']==i),'handoffs':handoffs(next(r for r in selected if r['task']==i))},
             'full_request':{'row':next(r for r in full if r['task']==i),'handoffs':handoffs(next(r for r in full if r['task']==i))}} for i in selection])
    original=next(r for r in main if r['task']=='user_task_15')
    q6={'original':original,'expanded':expanded[0],'original_handoffs':handoffs(original),'expanded_handoffs':handoffs(expanded[0])}
    summary={'groups':groups,'costs':costs,'ratios_of_medians':ratios,'context':context,'role_costs':role_costs,
             'total_model_call_ratio':costs['multi']['model_calls']['total']/costs['single']['model_calls']['total'],
             'experiment2':second,'question6':q6,'counts':{'baseline':len(base),'main':len(main),'full_request':len(full),'question6':len(expanded),'all':len(all_rows),'dev':len(all_rows)-71}}
    save('analysis/summary.json',summary)
    csv_file('analysis/comparison.csv',[{'group':name,'n':v['n'],'single_success':v['single_success'],'multi_success':v['multi_success'],'gained':';'.join(v['gained']),'lost':';'.join(v['lost'])} for name,v in groups.items()])
    csv_file('analysis/costs.csv',[{'architecture':name,'metric':key,**v} for name,data in costs.items() for key,v in data.items()])
    csv_file('analysis/roles.csv',[{'role':role,**values} for role,values in role_costs.items()])
    a={r['task']:r for r in selected};b={r['task']:r for r in full}
    csv_file('analysis/full_request.csv',[{'task':i,'subtask_success':a[i]['utility'],'full_success':b[i]['utility'],'subtask_input_tokens':a[i]['input_tokens'],'full_input_tokens':b[i]['input_tokens'],
        'subtask_peak':a[i]['max_input_tokens'],'full_peak':b[i]['max_input_tokens']} for i in selection])
    plots(summary)
    print('Analysis ready:',summary['counts'])
    return summary

def plots(s):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig,axes=plt.subplots(1,3,figsize=(12,3.6),layout='constrained')
    x=np.arange(3);values=list(s['groups'].values())
    for shift,key,label,color in [(-.18,'single_success','Один агент','#64748b'),(.18,'multi_success','Команда','#2563eb')]:
        bars=axes[0].bar(x+shift,[v[key] for v in values],.36,label=label,color=color);axes[0].bar_label(bars,padding=2)
    axes[0].set(xticks=x,xticklabels=['Все /30','Неск. сервисов /7','Один сервис /23'],ylabel='Решено задач',title='Успешность',ylim=(0,32));axes[0].tick_params(axis='x',labelsize=8);axes[0].legend(fontsize=8)
    v=[s['costs'][n]['model_calls'] for n in ['single','multi']]
    bars=axes[1].bar(['Один агент','Команда'],[a['median'] for a in v],color=['#64748b','#2563eb'])
    axes[1].bar_label(bars,fmt='%.1f',padding=3);axes[1].set(title='Медиана вызовов модели',ylabel='Вызовов за эпизод',ylim=(0,max(a['median'] for a in v)*1.3))
    for j,n in enumerate(['single','multi']):
        val=s['context'][n];axes[2].bar(j,val['median'],color=['#64748b','#2563eb'][j]);axes[2].plot(j,val['max'],'kx',markersize=9)
        axes[2].text(j,val['median'],str(round(val['median'])),ha='center',va='bottom',fontsize=8)
    axes[2].plot([],[],'kx',label='Максимум');axes[2].legend(fontsize=8)
    axes[2].set(xticks=[0,1],xticklabels=['Один агент','Команда'],title='Наибольший вход за эпизод',ylabel='Токены: медиана и максимум')
    fig.savefig('analysis/architecture.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(8,3),layout='constrained')
    exp=s['experiment2'];labels=['Только подзадача','Подзадача + запрос']
    bars=axes[0].bar(labels,[exp['pairs']['single_success'],exp['pairs']['multi_success']],color=['#2563eb','#15956b']);axes[0].bar_label(bars,padding=3);axes[0].set(title='Выбранные 10 задач',ylabel='Решено задач',ylim=(0,11))
    bars=axes[1].bar(labels,[exp['context'][n]['median'] for n in ['subtask','full_request']],color=['#2563eb','#15956b']);axes[1].bar_label(bars,fmt='%.0f',padding=3);axes[1].set(title='Медиана пикового входа',ylabel='Входные токены',ylim=(0,max(exp['context'][n]['median'] for n in ['subtask','full_request'])*1.25))
    fig.savefig('analysis/full_request.png',dpi=170);plt.close(fig)

if __name__=='__main__':
    import sys
    if len(sys.argv)>1 and sys.argv[1]=='select':select()
    else:analyze()
