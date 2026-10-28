import unittest
from fastapi.testclient import TestClient
from api.app import create_app
from cognitive_memory.storage.architecture import stable_id

class ObjectDetailTests(unittest.TestCase):
    def test_original_working_fields_and_owner_isolation(self):
        with TestClient(create_app(':memory:')) as client:
            memory=client.app.state.memory
            expected=memory.architecture.update_working_state('alice','chat','task',{'goals':['本次英文'],'task_state':{'count':0,'confirmed':False}})
            path='/api/architecture/objects/working_states/'+stable_id('alice','chat','task')
            self.assertEqual(client.get(path,params={'user_id':' ALICE '}).json(),expected)
            self.assertEqual(client.get(path,params={'user_id':'bob'}).status_code,404)
            self.assertEqual(client.get('/api/architecture/objects/not_a_table/x',params={'user_id':'alice'}).status_code,400)

    def test_chat_and_restored_session_return_actual_working_state(self):
        from langchain_core.messages import AIMessage
        from langchain_core.runnables import RunnableLambda

        class Model:
            def invoke(self, messages):
                return AIMessage(content='好的')
            def with_structured_output(self, schema, **kwargs):
                return RunnableLambda(lambda messages: schema.model_validate({'working_state_patch':{'goals':['制定周末计划'],'constraints':['本次简短']}}))

        with TestClient(create_app(':memory:', chat_model=Model())) as client:
            reply=client.post('/api/chat',json={'user_id':'alice','thread_id':'chat','task_id':'plan','message':'帮我制定周末计划，这次简短一点'}).json()
            self.assertEqual(reply['working_state']['goals'],['制定周末计划'])
            saved=client.get('/api/sessions/chat?user_id=alice').json()
            self.assertEqual(saved['task_id'],'plan')
            self.assertEqual(saved['working_state'],reply['working_state'])
            self.assertEqual(client.get('/api/sessions/chat?user_id=bob').status_code,404)
