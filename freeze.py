import hashlib,json,platform,subprocess,sys,importlib.metadata
from pathlib import Path
from run import read,save
if __name__=='__main__':
    old=read('reference/lr5_frozen.json')
    assert hashlib.sha256(Path('base_agent.py').read_bytes()).hexdigest()==old['hashes']['base_agent.py']
    assert hashlib.sha256(Path('prompts/system.txt').read_bytes()).hexdigest()==old['hashes'][str(Path('prompts')/'system.txt')]
    config=read('config.json');single=read('config_single.json')
    assert config['max_tools']==single['max_tools']==15
    assert config['context']==single['context']==16384
    assert config['model']==single['model']=='qwen3-4b'
    names=['multi_agent.py','base_agent.py','run.py','config.json','config_single.json','hypothesis.md']+[str(p) for p in Path('prompts').glob('*.txt')]
    value={'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
           'hashes':{name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in names},
           'python':sys.version,'executable':sys.executable,'platform':platform.platform(),
           'packages':{n:importlib.metadata.version(n) for n in ['agentdojo','openai','httpx','deepdiff']},
           'server_command':read('server_command.json'),'source_model':old['source_model'],
           'baseline':'first T=0 run from LR5; unchanged model, LR4 agent, prompt and limits'}
    model=Path(value['server_command'][value['server_command'].index('-m')+1])
    with model.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==value['source_model']
    save('frozen.json',value);print('Frozen:',value['commit'])
