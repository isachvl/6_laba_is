import json,time
from pathlib import Path
from base_agent import Agent as SingleAgent,StopEpisode,to_tool
from agentdojo.agent_pipeline.tool_execution import tool_result_to_str
from agentdojo.functions_runtime import FunctionCall,EmptyEnv
from agentdojo.types import ChatAssistantMessage,ChatSystemMessage,ChatUserMessage,ChatToolResultMessage,text_content_block_from_string as text

ROLES={'ask_email_agent':'email','ask_calendar_agent':'calendar','ask_files_agent':'files'}

def delegation_tools(expanded=False):
    descriptions={'email':'Read/search/send email and find contacts. No calendar or drive access.',
                  'calendar':'Read/search/create/update calendar events and obtain the current day. No email or drive access.',
                  'files':'Search/read/create/change/share drive files. No email or calendar access.'}
    if expanded:descriptions['email']='Read/search/send email, find contacts, and read/create/update calendar events. Can handle email-to-calendar tasks directly. No drive access.'
    return [{'type':'function','function':{'name':name,'description':descriptions[role],
             'parameters':{'type':'object','properties':{'task':{'type':'string','description':'A self-contained subtask, including known exact names, dates, IDs, addresses, requested action and required return facts.'}},'required':['task'],'additionalProperties':False}}}
            for name,role in ROLES.items()]

class MultiAgent(SingleAgent):
    def __init__(self,config,path,variant='multi'):
        super().__init__(config,'multi',path)
        self.variant=variant;self.role='orchestrator';self.delegation_id=0;self.next_id=0
        self.trace.update(variant=variant,role_costs={},delegations=0)
        self.original='';self.stand_log=[]

    def record(self,event):
        event.update(role=self.role,delegation_id=self.delegation_id)
        super().record(event)

    def model_for(self,chat,tools):
        if self.trace['tool_calls']>=self.config['max_tools']:raise StopEpisode('max_tools')
        if self.trace['model_calls']>=self.config['max_calls']:raise StopEpisode('max_calls')
        role=self.role
        before={k:self.trace[k] for k in ['model_calls','input_tokens','output_tokens']}
        start=time.perf_counter()
        try:return self.model(chat,tools)
        finally:
            cost=self.trace['role_costs'].setdefault(role,{'model_calls':0,'input_tokens':0,'output_tokens':0,'model_seconds':0.})
            for key in before:cost[key]+=self.trace[key]-before[key]
            cost['model_seconds']+=time.perf_counter()-start

    def execute_environment(self,call,runtime,env,chat,allowed):
        if self.trace['tool_calls']>=self.config['max_tools']:raise StopEpisode('max_tools')
        self.trace['tool_calls']+=1
        name=call['function']['name'];raw=call['function']['arguments'];args={};executed=False
        start=time.perf_counter()
        try:
            args=json.loads(raw)
            if not isinstance(args,dict):raise ValueError('Arguments must be an object')
            if name not in allowed:raise ValueError('Tool not available to this worker: '+name)
        except (ValueError,TypeError) as exc:output='Rejected tool call: '+str(exc);error=output
        else:
            result,error=runtime.run_function(env,name,args)
            executed=error is None
            output=tool_result_to_str(result) if error is None else str(error)
        # Only actual environment-tool names are admitted to the benchmark log.
        if name in runtime.functions:
            fc=FunctionCall(function=name,args=args,id=call['id'])
            self.stand_log.extend([ChatAssistantMessage(role='assistant',content=None,tool_calls=[fc]),
                ChatToolResultMessage(role='tool',content=[text(output)],tool_call_id=fc.id,tool_call=fc,error=error)])
        chat.append({'role':'tool','tool_call_id':call['id'],'content':output})
        self.record({'kind':'tool','name':name,'arguments_raw':raw,'arguments':args,'output':output,'error':error,
                     'executed':executed,'tool_number':self.trace['tool_calls'],'seconds':time.perf_counter()-start})

    def worker(self,role,task,runtime,env):
        previous=(self.role,self.delegation_id)
        self.next_id+=1;self.role=role;self.delegation_id=self.next_id
        allowed=list(self.config['worker_tools'][role])
        if self.variant=='email_calendar' and role=='email':allowed+=self.config['worker_tools']['calendar']
        prompt=Path('prompts/'+role+'.txt').read_text(encoding='utf-8')
        if self.variant=='email_calendar' and role=='email':prompt+='\nYou also have calendar tools and may complete email-to-calendar tasks directly.'
        request=task
        if self.variant=='full_request':request+='\n\nOriginal user request (context, not a replacement for this subtask):\n'+self.original
        chat=[{'role':'system','content':prompt},{'role':'user','content':request}]
        tools=[to_tool(runtime.functions[name]) for name in allowed]
        self.trace['delegations']+=1
        self.record({'kind':'delegation','task':task,'original_included':self.variant=='full_request','tools':allowed})
        answer='Stopped: worker_model_limit';reason='worker_model_limit'
        try:
            for _ in range(self.config['worker_calls']):
                result=self.model_for(chat,tools)
                calls=result.get('tool_calls',[])
                if not calls:
                    answer=result.get('content') or 'Unable to complete the subtask.';reason='answer';break
                chat.append({k:v for k,v in result.items() if k in ('role','content','tool_calls')})
                for call in calls:self.execute_environment(call,runtime,env,chat,allowed)
            self.record({'kind':'worker_return','task':task,'answer':answer,'reason':reason})
            return answer
        finally:self.role,self.delegation_id=previous

    def query(self,query,runtime,env=EmptyEnv(),messages=(),extra_args={}):
        start=time.perf_counter();self.original=query
        system=Path('prompts/orchestrator.txt').read_text(encoding='utf-8')
        if self.variant=='email_calendar':system+='\nThe email worker additionally has calendar tools and can complete email-to-calendar tasks without a second worker.'
        chat=[{'role':'system','content':system},{'role':'user','content':query}]
        self.stand_log=[ChatSystemMessage(role='system',content=[text(system)]),ChatUserMessage(role='user',content=[text(query)])]
        self.trace['query']=query;answer='Stopped: orchestrator_model_limit'
        try:
            for _ in range(self.config['orchestrator_calls']):
                result=self.model_for(chat,delegation_tools(self.variant=='email_calendar'))
                calls=result.get('tool_calls',[])
                if not calls:answer=result.get('content') or 'Unable to complete the task.';break
                chat.append({k:v for k,v in result.items() if k in ('role','content','tool_calls')})
                for call in calls:
                    name=call['function']['name']
                    try:
                        args=json.loads(call['function']['arguments'])
                        if name not in ROLES:raise ValueError('Orchestrator may only delegate to workers')
                        if not isinstance(args,dict) or set(args)!={'task'} or not isinstance(args['task'],str):raise ValueError('Expected one string task')
                    except (ValueError,TypeError) as exc:
                        output='Invalid delegation: '+str(exc)
                        self.record({'kind':'delegation_error','call':call,'error':output})
                    else:output=self.worker(ROLES[name],args['task'],runtime,env)
                    chat.append({'role':'tool','tool_call_id':call['id'],'content':output})
            else:self.trace['reason']='orchestrator_model_limit'
        except StopEpisode as exc:self.trace['reason']=str(exc);answer='Stopped: '+str(exc)
        except Exception as exc:
            self.trace['reason']='runtime_error';answer='Unable to complete the task: '+type(exc).__name__
            self.record({'kind':'exception','error':repr(exc)})
        self.stand_log.append(ChatAssistantMessage(role='assistant',content=[text(answer)],tool_calls=None))
        stand_calls=[call for message in self.stand_log if message['role']=='assistant' for call in (message.get('tool_calls') or [])]
        self.trace.update(answer=answer,seconds=time.perf_counter()-start,
                          stand_calls=[{'name':c.function,'arguments':c.args,'id':c.id} for c in stand_calls])
        self.save()
        return query,runtime,env,self.stand_log,extra_args
