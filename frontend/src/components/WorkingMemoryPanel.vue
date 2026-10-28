<script setup>
defineProps({ memory: { type: Object, default: null }, sending: Boolean });
</script>
<template>
  <aside class="working-panel" aria-label="当前对话工作记忆">
    <header><span class="working-dot"/><h2>工作记忆</h2><span class="working-live">{{ sending?'更新中':memory?'当前任务':'尚未开始' }}</span></header>
    <p class="working-intro">当前对话正在处理的目标与上下文。</p>
    <section><h3>当前目标 <small>goals</small></h3><ul v-if="memory?.goals?.length"><li v-for="(goal,i) in memory.goals" :key="i">{{ goal }}</li></ul><p v-else class="working-empty">尚未提取到明确目标</p></section>
    <section><h3>临时约束 <small>constraints</small></h3><ul v-if="memory?.constraints?.length"><li v-for="(item,i) in memory.constraints" :key="i">{{ item }}</li></ul><p v-else class="working-empty">暂无本次任务约束</p></section>
    <section><h3>待确认问题 <small>open_questions</small></h3><ul v-if="memory?.open_questions?.length"><li v-for="(item,i) in memory.open_questions" :key="i">{{ item }}</li></ul><p v-else class="working-empty">暂无待确认问题</p></section>
    <details v-if="memory"><summary>查看完整工作状态</summary><pre>{{ JSON.stringify(memory,null,2) }}</pre></details>
    <footer>随本次对话更新；切换会话后显示对应任务。它不属于长期记忆星图。</footer>
  </aside>
</template>
<style scoped>
.working-panel{padding:22px 18px;background:var(--panel,#15151a);border-left:1px solid var(--line,#303039);overflow:auto;min-width:0}header{display:flex;align-items:center;gap:8px}header h2{font-size:13px;margin:0;font-weight:500}.working-dot{width:6px;height:6px;border-radius:50%;background:#d5b484}.working-live{font-size:10px;color:var(--muted,#92939d);margin-left:auto}.working-intro{font-size:11px;line-height:1.8;color:#92939d;margin:12px 0 24px}section{border-top:1px solid var(--line,#303039);padding:17px 0}h3{font-size:11px;font-weight:500;margin:0 0 13px;color:#d0c9e0}h3 small{display:block;font:9px/1.6 monospace;color:#70717e;margin-top:3px}ul{padding-left:16px;margin:0;font-size:12px;line-height:1.9;overflow-wrap:anywhere}li+li{margin-top:8px}.working-empty{font-size:11px;line-height:1.8;color:#7e808d;margin:0}summary{font-size:11px;color:#a2a4b4;cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:10px/1.8 monospace;margin-top:13px;color:#aeb6c5}footer{font-size:10px;line-height:1.9;color:#747885;margin-top:24px}
@media(max-width:1050px){.working-panel{border-left:0;border-top:1px solid var(--line,#303039);max-height:none}.working-panel section{display:inline-block;vertical-align:top;width:31%;margin-right:2%;box-sizing:border-box}}@media(max-width:650px){.working-panel section{display:block;width:100%;margin:0}}
</style>
