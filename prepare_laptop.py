import json,os,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def load(p):return [json.loads(l) for l in Path(p).read_text(encoding='utf-8').splitlines()]

def main():
    os.chdir(ROOT);os.environ['MLFLOW_DISABLE_AGENT_HINT']='1'
    import mlflow
    from mlflow.tracking import MlflowClient
    base=load('baseline/results.jsonl');main=load('results/main.jsonl');full=load('results/full_request.jsonl')
    selected=json.loads(Path('selection.json').read_text(encoding='utf-8'))['tasks']
    groups={'single_30':base,'multi_30':main,'multi_selected_10':[r for r in main if r['task'] in selected],'full_request_10':full}
    mlflow.set_tracking_uri('sqlite:///'+(ROOT/'mlflow.db').as_posix());mlflow.set_experiment('lr6');client=MlflowClient();exp=mlflow.get_experiment_by_name('lr6')
    for name,group in groups.items():
        old=client.search_runs([exp.experiment_id],filter_string=f"tags.configuration = '{name}'")
        with mlflow.start_run(run_id=old[0].info.run_id if old else None,run_name=name,log_system_metrics=False):
            mlflow.set_tag('configuration',name);mlflow.log_params({'episodes':len(group),'temperature':0,'max_environment_tools':15})
            metrics={'success':sum(r['utility'] for r in group)/len(group),'median_model_calls':statistics.median(r['model_calls'] for r in group),
                     'median_input_tokens':statistics.median(r['input_tokens'] for r in group),'median_peak_input_tokens':statistics.median(r['max_input_tokens'] for r in group)}
            previous=old[0].data.metrics if old else {};pending={k:v for k,v in metrics.items() if previous.get(k)!=v}
            if pending:mlflow.log_metrics(pending)
            if name=='multi_30':
                for path in Path('analysis').glob('*'):
                    if path.is_file():mlflow.log_artifact(str(path),'analysis')
                mlflow.log_artifact('report.pdf','report')
                mlflow.log_artifact('results.jsonl','results')
                mlflow.log_artifact('selection.json','configuration');mlflow.log_artifact('frozen.json','configuration')
                mlflow.log_artifacts('traces','traces/lr6');mlflow.log_artifacts('baseline/traces','traces/lr5_baseline')
    print('MLflow ready: experiment lr6; 4 runs, 4 metrics, 2 graph images. Shared plots/report/traces: multi_30 -> Artifacts.')
if __name__=='__main__':main()
