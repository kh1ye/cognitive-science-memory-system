import assert from 'node:assert/strict';
import { test } from 'node:test';
import { registerMemoryTools } from './register.mjs';

test('rejects missing user and non-local or redirected origins', () => {
  assert.throws(() => registerMemoryTools({pluginConfig:{},registerTool(){}}));
  for (const baseUrl of ['https://example.com','http://127.0.0.1/path','http://user@localhost','http://localhost/?x=1'])
    assert.throws(() => registerMemoryTools({pluginConfig:{userId:'alice',baseUrl},registerTool(){}}));
});
test('registers explicit tools and forwards privacy decisions, identity and failures', async () => {
  const tools=[];
  registerMemoryTools({pluginConfig:{userId:' Alice '},registerTool:t=>tools.push(t)});
  assert.deepEqual(tools.map(t=>t.name),['cognitive_memory_search','cognitive_memory_save']);
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async (_url,options)=>{
      const data=JSON.parse(options.body);
      assert.equal(data.user_id,'alice');
      assert.equal(data.consent,false);
      assert.deepEqual(data.tags,['sensitive']);
      return {ok:true,json:async()=>({decision:'DROP',reason:'consent_required'})};
    };
    const result=await tools[1].execute('1',{content:'private',sensitive:true,user_id:'attacker',consent:true});
    assert.equal(result.details.decision,'DROP');
    globalThis.fetch=async()=>{throw new Error('offline')};
    assert.equal((await tools[0].execute('2',{query:'Python'})).isError,true);
  } finally {globalThis.fetch=original;}
});
test('round trips with the real temporary API when supplied', {skip:!process.env.MEMORY_TEST_URL}, async()=>{
  const tools=[];
  registerMemoryTools({pluginConfig:{userId:'node-integration',baseUrl:process.env.MEMORY_TEST_URL},registerTool:t=>tools.push(t)});
  const write=await tools[1].execute('1',{content:'我喜欢 Python',memory_key:'language',memory_value:'Python'});
  assert.equal(write.details.decision,'WRITE_CURRENT');
  const found=await tools[0].execute('2',{query:'Python'});
  assert.equal(found.details.results[0].source,'openclaw_plugin');
  for (const memory_type of ['episodic','semantic','procedural']) {
    const saved=await tools[1].execute('typed',{content:`${memory_type} from OpenClaw`,memory_type});
    assert.equal(saved.details.memory.memory_type,memory_type);
  }
  assert.equal((await tools[1].execute('bad-type',{content:'invalid',memory_type:'working'})).isError,true);
  const blocked=await tools[1].execute('3',{content:'敏感内容',sensitive:true});
  assert.equal(blocked.details.decision,'DROP');
  const optout=await tools[1].execute('4',{content:'不要记住我的偏好'});
  assert.equal(optout.details.decision,'DROP');
});
