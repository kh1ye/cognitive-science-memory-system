"""Adapter HTTP contract tests. Host runtime activation is not simulated as an E2E pass."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

import uvicorn
from api.app import create_app

ROOT = Path(__file__).resolve().parents[1]


class AgentIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.sock = socket.socket()
        cls.sock.bind(('127.0.0.1', 0))
        cls.url = f'http://127.0.0.1:{cls.sock.getsockname()[1]}'
        cls.server = uvicorn.Server(uvicorn.Config(create_app(Path(cls.temp.name) / 'test.db', demo_token='', chat_db_path=':memory:'), log_level='error'))
        cls.thread = threading.Thread(target=lambda: cls.server.run(sockets=[cls.sock]), daemon=True)
        cls.thread.start()
        for _ in range(100):
            if cls.server.started:
                break
            time.sleep(.05)
        if not cls.server.started:
            raise RuntimeError('Temporary API did not start')

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(10)
        cls.sock.close()
        cls.temp.cleanup()

    def load_provider(self, home, user='alice', **context):
        # Only host discovery/config plumbing is stubbed; requests go to a real API.
        agent = types.ModuleType('agent')
        host = types.ModuleType('agent.memory_provider')
        host.MemoryProvider = object
        utils = types.ModuleType('utils')
        utils.read_json_or_empty = lambda path: json.loads(path.read_text()) if path.exists() else {}
        utils.atomic_json_write = lambda path, values: path.write_text(json.dumps(values))
        spec = importlib.util.spec_from_file_location('cognitive_provider', ROOT / 'integrations/hermes/cognitive-memory/__init__.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'agent': agent, 'agent.memory_provider':host, 'utils':utils}):
            spec.loader.exec_module(module)
            provider = module.CognitiveMemoryProvider()
            self.assertTrue(provider.is_available())
            provider.save_config({'base_url':self.url,'user_id':user}, str(home))
            provider.initialize('test-session',hermes_home=str(home),**context)
        return provider

    def test_hermes_real_write_search_and_privacy(self):
        with tempfile.TemporaryDirectory() as home:
            provider = self.load_provider(home)
            call = lambda name, args: json.loads(provider.handle_tool_call(name, args))
            result = call('cognitive_memory_save', {'content':'我喜欢喝茶','memory_key':'drink','memory_value':'茶'})
            self.assertEqual(result['decision'],'WRITE_CURRENT')
            result = call('cognitive_memory_search', {'query':'茶'})
            self.assertEqual(result['results'][0]['source'],'hermes_plugin')
            self.assertEqual(result['results'][0]['user_id'],'alice')
            self.assertEqual(call('cognitive_memory_save',{'content':'敏感输入','sensitive':True})['decision'],'DROP')
            self.assertEqual(call('cognitive_memory_save',{'content':'不要记住这个偏好'})['decision'],'DROP')
            self.assertIn('error',call('cognitive_memory_search', {'query':''}))
            self.assertIn('error',json.loads(provider.handle_tool_call('cognitive_memory_search',{'query':'茶'},hermes_home=str(Path(home)/'other'))))

    def test_profile_and_gateway_isolation_and_subagent_write_block(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            a = self.load_provider(first,user='')
            b = self.load_provider(second,user='')
            self.assertNotEqual(a.user_id,b.user_id)
            c = self.load_provider(first,user='',user_id='gateway-user')
            self.assertNotEqual(a.user_id,c.user_id)
            subagent = self.load_provider(second,user='',agent_context='subagent')
            self.assertIn('error',json.loads(subagent.handle_tool_call('cognitive_memory_save',{'content':'test'})))
            self.assertRaises(ValueError,a._validate_url,'https://external.example')
            a.base_url = 'http://127.0.0.1:1'
            self.assertIn('error',json.loads(a.handle_tool_call('cognitive_memory_search',{'query':'tea'})))

    def test_installer_preserves_existing_config(self):
        spec = importlib.util.spec_from_file_location('installer',ROOT / 'integrations/install_hermes.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as home:
            config = Path(home)/'cognitive-memory.json'
            config.write_text('{"user_id":"existing"}')
            module.install(home,'replacement')
            self.assertEqual(json.loads(config.read_text())['user_id'],'existing')
            self.assertTrue((Path(home)/'plugins/cognitive-memory/plugin.yaml').exists())

    def test_hermes_saves_all_three_types_and_rejects_working_type(self):
        with tempfile.TemporaryDirectory() as home:
            provider = self.load_provider(home, user='three-types')
            for memory_type in ('episodic', 'semantic', 'procedural'):
                result = json.loads(provider.handle_tool_call('cognitive_memory_save', {
                    'content': f'{memory_type} type from Hermes', 'memory_type': memory_type,
                }))
                self.assertEqual(result['memory']['memory_type'], memory_type)
            self.assertIn('error', json.loads(provider.handle_tool_call('cognitive_memory_save', {
                'content': 'invalid', 'memory_type': 'working',
            })))

    @unittest.skipUnless(shutil.which('node'), 'Node is required for OpenClaw adapter contracts')
    def test_openclaw_real_http_contract(self):
        result = subprocess.run(['node','--test','integrations/openclaw/plugin.test.mjs'],cwd=ROOT,env={**os.environ,'MEMORY_TEST_URL':self.url},capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    @unittest.skipUnless((ROOT / 'integrations/deepseek-harness/node_modules/@deepseek-ai/dsh-tools').exists(), 'Run npm ci in integrations/deepseek-harness for official runtime tests')
    def test_deepseek_harness_official_runtime_and_real_api(self):
        result = subprocess.run(['node','--test','integrations/deepseek-harness/plugin.test.mjs'],cwd=ROOT,env={**os.environ,'MEMORY_TEST_URL':self.url},capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
