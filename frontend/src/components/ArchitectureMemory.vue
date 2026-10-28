<script setup>
import { computed, ref, watch } from 'vue';
import { api, post } from '../lib/api';
const props = defineProps({ user: { type: String, required: true }, catalog: Array });
const emit = defineEmits(['changed']);
const expanded = ref(false), module = ref('working_states'), items = ref([]), error = ref(''), busy = ref(false);
const thread = ref('manual'), task = ref('task'), content = ref(''), analysis = ref('{}'), receipt = ref(null);
const policy = ref('persist'), argumentsText = ref('{"text":"hello   world"}');
const modules = {working_states:'工作状态', episode_events:'情景事件', semantic_assertions:'语义断言', semantic_documents:'文档知识', procedure_versions:'程序版本', procedure_runs:'执行记录', learning_operations:'学习回执', source_records:'来源'};
const columns = computed(() => ({working_states:['thread_id','task_id','revision','status','goals','constraints','active_knowledge','task_state'],episode_events:['occurred_at','recorded_at','sequence_no','actor','observation','action_ref','outcome','source_refs'],semantic_assertions:['subject','predicate','value','scope','valid_from','valid_to','status','version','epistemic_status','source_refs'],semantic_documents:['document_id','document_version','section_or_locator','content','scope','source_refs'],procedure_versions:['description','kind','implementation_ref','version','status','validation_refs','input_schema'],procedure_runs:['version_id','version','status','result','error'],learning_operations:['target_module','status','result_refs','error'],source_records:['source_kind','source_event_id','source_ref','content','scope']}[module.value]));
const show = value => typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—');
async function load() {
  const user = props.user, selected = module.value;
  error.value=''; busy.value=true;
  try { const data = await api(`/api/architecture/objects/${selected}?user_id=${encodeURIComponent(user)}`); if (props.user===user && module.value===selected) items.value=data.items; }
  catch(e) { error.value=e.message; } finally { busy.value=false; }
}
async function run(action) { error.value=''; try {receipt.value=await action(); emit('changed'); await load();} catch(e){error.value=e.message;} }
function observe() { return run(() => post('/api/architecture/observe',{observation:{user_id:props.user,thread_id:thread.value,task_id:task.value,source_kind:'user_report',source_event_id:crypto.randomUUID(),content:content.value,retention_policy:policy.value},analysis:JSON.parse(analysis.value)})); }
function install(){return run(()=>post('/api/architecture/procedures/install-builtins',{user_id:props.user}));}
function execute(row){return run(()=>post(`/api/architecture/runs/${row.id}`,{user_id:props.user,run_key:crypto.randomUUID(),thread_id:thread.value,task_id:task.value,arguments:JSON.parse(argumentsText.value)}));}
function change(row,action){return run(()=>post(`/api/architecture/procedures/${row.id}/${action}`,{user_id:props.user}));}
function remove(row){return run(()=>api(`/api/architecture/sources/${row.id}?user_id=${encodeURIComponent(props.user)}`,{method:'DELETE'}));}
watch(module,()=>{items.value=[];if(expanded.value)load();});
watch(()=>props.catalog,()=>{if(expanded.value)load();});
watch(()=>props.user,()=>{items.value=[];receipt.value=null;error.value='';content.value='';if(expanded.value)load();});
async function toggle(){expanded.value=!expanded.value;if(expanded.value)await load();}
</script>
<template>
<section class="panel architecture-memory">
  <button class="button" @click="toggle">{{ expanded ? '收起' : '打开' }}四类记忆 · 任务与来源</button>
  <div v-if="expanded">
    <p>工作状态按任务恢复；事件、知识和程序分别保存。下方列表汇总四类对象与兼容记录，此处可查看专属字段、来源与执行结果。</p>
    <label>模块 <select v-model="module"><option v-for="(label,key) in modules" :key="key" :value="key">{{label}}</option></select></label>
    <button @click="load" :disabled="busy">刷新</button>
    <p v-if="error" role="alert">{{error}}</p>
    <form @submit.prevent="observe">
      <label>会话 <input v-model="thread" required></label><label>任务 <input v-model="task" required></label>
      <label>观察 <textarea v-model="content" required placeholder="输入原始观察；自动语义提取可使用个人助手"></textarea></label>
      <label>保存策略 <select v-model="policy"><option value="persist">允许长期保存</option><option value="no_long_term">仅任务状态（仍持久化）</option><option value="no_persist">不持久化正文或检查点</option></select></label>
      <details><summary>结构化分流（可选 JSON，离线校验）</summary><textarea v-model="analysis" aria-label="结构化分流"></textarea><p>默认 {} 只记录工作观察。语义候选需 evidence_text 原文依据；程序提议需验证后启用。</p></details>
      <button type="submit">提交观察</button>
    </form>
    <template v-if="module==='procedure_versions'"><button @click="install">登记内置程序</button><label>执行参数 JSON <input v-model="argumentsText"></label></template>
    <p v-if="!items.length && !busy">该用户暂无此类记录。</p>
    <article v-for="row in items" :key="row.id" class="architecture-record">
      <code>{{row.id || `${row.thread_id}/${row.task_id}`}}</code>
      <dl><template v-for="key in columns" :key="key"><dt>{{key}}</dt><dd>{{show(row[key])}}</dd></template></dl>
      <template v-if="module==='procedure_versions'"><button v-if="row.status==='enabled'" @click="execute(row)">执行</button><button v-if="row.status==='draft'" @click="change(row,'validate')">验证</button><button v-if="['validated','disabled'].includes(row.status)" @click="change(row,'activate')">启用此版本</button><button v-if="row.status==='enabled'" @click="change(row,'disable')">停用</button></template>
      <button v-if="module==='source_records'" @click="remove(row)">删除来源及派生内容</button>
    </article>
    <details v-if="receipt" open><summary>本次实际回执</summary><pre>{{JSON.stringify(receipt,null,2)}}</pre></details>
  </div>
</section>
</template>
<style scoped>
.architecture-memory{padding:1rem;margin-bottom:1rem}.architecture-memory label{display:block;margin:.5rem 0}.architecture-memory textarea{display:block;width:100%;min-height:4rem}.architecture-record{border-top:1px solid var(--border,#ddd);padding:1rem 0;overflow-wrap:anywhere}.architecture-record dl{display:grid;grid-template-columns:minmax(8rem,1fr) 4fr;gap:.3rem}.architecture-record dd{margin:0}.architecture-memory pre{white-space:pre-wrap;overflow-wrap:anywhere}
</style>
