import json,tempfile,unittest
from pathlib import Path
from agentdojo.task_suite.load_suites import get_suites
from multi_agent import MultiAgent,ROLES


def call(name,args,number):
    return {'id':'test_'+str(number),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}

def message(c=None,content=''):
    value={'role':'assistant','content':content}
    if c:value['tool_calls']=[c]
    return value

class ScriptedAgent(MultiAgent):
    def __init__(self,config,path,scripts,variant='multi'):
        super().__init__(config,path,variant);self.scripts={r:list(v) for r,v in scripts.items()}
    def model(self,chat,tools=None,schema=None):
        result=self.scripts[self.role].pop(0);self.trace['model_calls']+=1
        self.record({'kind':'model','messages':chat.copy(),'tools':tools,'response':result,'usage':{'prompt_tokens':0,'completion_tokens':0},'seconds':0.})
        return result

class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=json.loads(Path('config.json').read_text());cls.suite=get_suites('v1.2.2')['workspace']
    def close(self,agent):agent.client.close();agent.http.close()

    def test_scripted_files_then_email_matches_task33(self):
        task=self.suite.get_user_task_by_id('user_task_33')
        env=task.init_environment(self.suite.load_and_inject_default_environment({}))
        expected=task.ground_truth(env)
        role_of={name:role for role,names in self.config['worker_tools'].items() for name in names}
        scripts={'orchestrator':[
            message(call('ask_files_agent',{'task':'Read client-meeting-minutes.docx; return client, next meeting YYYY-MM-DD, summary and attachment file ID.'},'d1')),
            message(call('ask_email_agent',{'task':'Send Summary of the client meeting with the supplied summary/date and file attachment: '+json.dumps(expected[-1].args)},'d2')),
            message(content='The requested summary and attachment were sent.')], 'files':[],'email':[]}
        for i,item in enumerate(expected):scripts[role_of[item.function]].append(message(call(item.function,item.args,i)))
        scripts['files'].append(message(content='Exact requested facts and identifiers: '+json.dumps(expected[-1].args)))
        scripts['email'].append(message(content='The requested message and attachment were sent.'))
        with tempfile.TemporaryDirectory() as folder:
            a=ScriptedAgent(self.config,Path(folder)/'trace.json',scripts)
            try:
                success,_=self.suite.run_task_with_pipeline(a,task,None,{})
                self.assertTrue(success)
                actual=[(c['name'],c['arguments']) for c in a.trace['stand_calls']]
                self.assertEqual(actual,[(c.function,c.args) for c in expected])
                self.assertFalse(any(name.startswith('ask_') for name,args in actual))
                roles=[e['role'] for e in a.trace['events'] if e['kind']=='delegation']
                self.assertEqual(roles,['files','email'])
                first=[e for e in a.trace['events'] if e['kind']=='model' and e['role']=='email'][0]
                self.assertEqual(len(first['messages']),2)
                self.assertEqual(first['messages'][1]['content'],next(e['task'] for e in a.trace['events'] if e['kind']=='delegation' and e['role']=='email'))
            finally:self.close(a)

    def test_shared_limit_stops_at_15_across_workers(self):
        scripts={'orchestrator':[message(call('ask_files_agent',{'task':'List files seven times.'},'d1')),message(call('ask_email_agent',{'task':'Read sent emails eight times.'},'d2'))],
            'files':[message(call('list_files',{},i)) for i in range(7)]+[message(content='Listed files.')],
            'email':[message(call('get_sent_emails',{},i+7)) for i in range(8)]}
        with tempfile.TemporaryDirectory() as folder:
            a=ScriptedAgent(self.config,Path(folder)/'trace.json',scripts)
            try:
                a.query('Exercise the shared tool budget.',self._runtime(),self.suite.load_and_inject_default_environment({}))
                self.assertEqual(a.trace['tool_calls'],15)
                self.assertEqual(len(a.trace['stand_calls']),15)
                self.assertEqual(a.trace['reason'],'max_tools')
                self.assertEqual([c['name'] for c in a.trace['stand_calls']],['list_files']*7+['get_sent_emails']*8)
            finally:self.close(a)

    def test_role_restriction_rejects_other_service(self):
        scripts={'orchestrator':[message(call('ask_email_agent',{'task':'Do not access other services.'},'d1')),message(content='Finished.')],
                 'email':[message(call('create_calendar_event',{},0)),message(content='Calendar tools are not available.') ]}
        with tempfile.TemporaryDirectory() as folder:
            a=ScriptedAgent(self.config,Path(folder)/'trace.json',scripts)
            try:
                a.query('Role restriction test.',self._runtime(),self.suite.load_and_inject_default_environment({}))
                event=next(e for e in a.trace['events'] if e['kind']=='tool')
                self.assertFalse(event['executed']);self.assertIn('not available',event['error'])
                self.assertEqual(a.trace['tool_calls'],1)
            finally:self.close(a)

    def _runtime(self):
        from agentdojo.functions_runtime import FunctionsRuntime
        return FunctionsRuntime(self.suite.tools)

if __name__=='__main__':unittest.main()
