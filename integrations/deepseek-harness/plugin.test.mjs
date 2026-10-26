import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createServer } from 'node:http';
import { Context } from '@deepseek-ai/cordis';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import Tools from '@deepseek-ai/dsh-tools';
import * as plugin from './index.js';

async function runtime(baseUrl, userId='dsh-contract') {
  const ctx=new Context();
  const prompt=ctx.plugin(SystemPrompt,{});
  await prompt.await();
  const tools=ctx.plugin(Tools,{});
  await tools.await();
  const memory=ctx.plugin(plugin,{baseUrl,userId});
  await memory.await();
  return {ctx, close:async()=>{await memory.dispose();await tools.dispose();await prompt.dispose();}};
}
function execute(ctx,name,args,signal=new AbortController().signal) {
  return ctx.tools.execute({callId:'memory-test',name,arguments:args,signal});
}

test('official Cordis/Tools registers, validates and unregisters memory tools',async()=>{
  const app=await runtime('http://127.0.0.1:1');
  assert.deepEqual(app.ctx.tools.schemas().map(t=>t.name),['cognitive_memory_search','cognitive_memory_save']);
  assert.equal((await execute(app.ctx,'cognitive_memory_search',{query:''})).isError,true);
  assert.equal((await execute(app.ctx,'cognitive_memory_search',{query:'tea',top_k:21})).isError,true);
  assert.equal((await execute(app.ctx,'cognitive_memory_save',{content:'tea',consent:true})).isError,true);
  const failed=await execute(app.ctx,'cognitive_memory_search',{query:'tea'});
  assert.equal(failed.isError,true);
  assert.equal(failed.value,undefined);
  await app.close();
  assert.deepEqual(app.ctx.get('tools'),undefined);
});

test('forwards fixed namespace, preserves privacy decisions and cancellation',async()=>{
  const server=createServer(async(req,res)=>{
    let raw='';for await(const part of req)raw+=part;
    const body=JSON.parse(raw);
    assert.equal(body.user_id,'alice');
    assert.equal(body.source,'deepseek_harness_plugin');
    assert.equal(body.consent,false);
    assert.deepEqual(body.tags,['sensitive']);
    res.setHeader('Content-Type','application/json');
    res.end(JSON.stringify({decision:'DROP',reason:'consent_required'}));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const app=await runtime(`http://127.0.0.1:${server.address().port}`,' Alice ');
  try {
    const result=await execute(app.ctx,'cognitive_memory_save',{content:'sensitive fact',sensitive:true});
    assert.equal(result.isError,false);
    assert.equal(JSON.parse(result.value.result).decision,'DROP');
    const cancelled=AbortSignal.abort();
    assert.equal((await execute(app.ctx,'cognitive_memory_search',{query:'tea'},cancelled)).isError,true);
    assert.throws(()=>plugin.apply({tools:{}},{baseUrl:'https://example.com',userId:'alice'}));
  } finally {await app.close();await new Promise(resolve=>server.close(resolve));}
});

test('real temporary memory API: write, recall, conflict, privacy and namespace isolation', {skip:!process.env.MEMORY_TEST_URL},async()=>{
  const app=await runtime(process.env.MEMORY_TEST_URL);
  const call=async(name,args)=>{
    const result=await execute(app.ctx,name,args);
    assert.equal(result.isError,false,JSON.stringify(result));
    return JSON.parse(result.value.result);
  };
  try {
    const first=await call('cognitive_memory_save',{content:'我喜欢喝茶',memory_key:'drink',memory_value:'茶'});
    assert.equal(first.decision,'WRITE_CURRENT');
    const found=await call('cognitive_memory_search',{query:'茶'});
    assert.equal(found.results[0].source,'deepseek_harness_plugin');
    assert.equal(found.results[0].user_id,'dsh-contract');
    const changed=await call('cognitive_memory_save',{content:'我现在更喜欢喝咖啡',memory_key:'drink',memory_value:'咖啡'});
    assert.equal(changed.decision,'CANDIDATE');
    assert.equal((await call('cognitive_memory_save',{content:'secret',sensitive:true})).decision,'DROP');
    assert.equal((await call('cognitive_memory_save',{content:'不要记住这个偏好'})).decision,'DROP');
    const other=await runtime(process.env.MEMORY_TEST_URL,'different-user');
    try {
      const empty=await execute(other.ctx,'cognitive_memory_search',{query:'茶'});
      assert.equal(JSON.parse(empty.value.result).results.length,0);
    } finally {await other.close();}
  } finally {await app.close();}
});
