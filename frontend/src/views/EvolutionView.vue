<script setup>
import { computed, onUnmounted, ref } from "vue";
import { useWorkspace } from "../composables/useWorkspace";
import { post } from "../lib/api";
import { eventNames, roles, types } from "../lib/format";
import { afterState, decisionSummary, evidenceParts, metricExplanation } from "../lib/evolution";

const { state, refresh } = useWorkspace();
const content = ref("");
const busy = ref(false);
const error = ref("");
const report = ref(null);
const records = computed(() => report.value?.traces.filter((trace) => trace.result.memory) || []);
const statusNames = { done: "已执行", blocked: "已拦截", skipped: "已跳过" };
const methodNames = { model: "模型自动提取", local_rules: "本地规则提取 · 有限范围", privacy_gate: "隐私门预检查" };
const highlightedInput = computed(() => report.value ? evidenceParts(report.value.input.content, report.value.extraction.candidates) : []);
const ending = computed(() => {
  if (!report.value) return "";
  if (report.value.outcome === "no_new_memory") return "没有写入新的记忆";
  if (report.value.outcome === "privacy_blocked") return "遵循你的要求，未保存正文";
  return report.value.traces.length === 1 ? decisionSummary(report.value.traces[0]) : `本次处理了 ${report.value.traces.length} 条候选，各自的变化如下。`;
});
let active = true;
onUnmounted(() => { active = false; });
async function analyze() {
  if (busy.value || !content.value.trim()) return;
  busy.value = true;
  error.value = "";
  report.value = null;
  try {
    const result = await post("/api/evolution/analyze", {
      content: content.value.trim(), user_id: state.user,
    }, { timeoutMs: 240000 });
    if (!active) return;
    report.value = result;
    await refresh();
  } catch (failure) {
    if (active) error.value = failure.message;
  } finally {
    if (active) busy.value = false;
  }
}
</script>

<template>
  <div class="page evolution-page">
    <div class="page-heading">
      <div><h1>记忆演化</h1><p>输入一句话，完整看见它如何被理解、筛选并存储。</p></div>
      <span class="evolution-label">一次输入 · 全程可见</span>
    </div>

    <section class="panel input-panel">
      <div class="input-heading"><div><span class="eyebrow">从你的原话开始</span><h2>这次，有什么想让系统记住？</h2></div><span class="user-label">当前用户：{{ state.user }}</span></div>
      <form @submit.prevent="analyze">
        <label class="sr-only" for="evolution-content">输入想让系统记住的信息</label>
        <textarea id="evolution-content" v-model="content" rows="3" required maxlength="10000" :disabled="busy" placeholder="例如：我现在更喜欢喝茶。" />
        <div class="submit-row"><p>无需填写记忆类型或参数。系统自动提取并执行真实写入，下面一次展开全部结果。</p><button class="button primary" type="submit" :disabled="busy || !content.trim()">{{ busy ? '正在分析…' : '查看记忆全过程' }} <span aria-hidden="true">→</span></button></div>
      </form>
      <p class="scope-note">已配置模型时自动提取；未配置时仅识别简单的饮品、编程语言偏好。提交会处理并保存通过筛选的信息，敏感候选不会自动授权保存。</p>
      <p v-if="error" class="local-error" role="alert">{{ error }}<span v-if="error.includes('接口不存在')"> 请先重启后端以加载新接口。</span></p>
    </section>

    <section v-if="busy" class="panel processing" role="status"><span class="pulse" aria-hidden="true" /><div><h2>正在自动处理这次输入</h2><p>提取信息 → 选择性编码 → 比较已有记忆 → 巩固决策 → 返回存储记录</p><p>等待实际结果后完整展示，无需逐步操作。</p></div></section>
    <div v-else-if="!report" class="empty-evolution"><span aria-hidden="true">◎</span><h2>一条输入，一段完整的记忆轨迹</h2><p>原话 → 提取结果 → 认知处理 → 新旧变化 → 最终存储</p><small>展示真实执行结果，不会自动生成额外确认或虚构证据。</small></div>

    <section v-if="report" class="journey" aria-label="完整记忆演化过程" aria-live="polite">
      <div class="panel outcome-summary"><span class="eyebrow">先看结论 · 本次处理已完成</span><h2>{{ ending }}</h2><ul v-if="report.traces.length > 1" class="summary-list"><li v-for="(trace, index) in report.traces" :key="index">候选 {{ index + 1 }}：{{ decisionSummary(trace) }}</li></ul><p v-if="report.outcome === 'no_new_memory'" class="explanation-note">{{ report.message }}</p><div class="summary-meta"><span>{{ records.length }} 条记录返回</span><span>{{ methodNames[report.extraction.method] }}</span><span>本次快照 · 不代表所有历史记录</span></div></div>

      <article class="journey-stage">
        <span class="stage-number" aria-hidden="true">01</span>
        <div class="panel stage-content"><div class="stage-heading"><h2>用户原话</h2><span class="status-tag done">已接收</span></div><blockquote class="evidence-input"><template v-for="(part, index) in highlightedInput" :key="index"><mark v-if="part.highlighted" :title="part.label">{{ part.text }}</mark><span v-else>{{ part.text }}</span></template></blockquote><p class="explanation-note">{{ report.extraction.candidates.length ? '高亮片段是下方提取结果的原文依据。' : '本次没有用于提取的有效原文片段。' }} 归属用户：{{ report.input.user_id }}。</p></div>
      </article>

      <article class="journey-stage">
        <span class="stage-number" aria-hidden="true">02</span>
        <div class="panel stage-content"><div class="stage-heading"><h2>自动提取信息</h2><span class="status-tag">{{ methodNames[report.extraction.method] }}</span></div><p class="step-description">{{ report.extraction.message }}</p>
          <div v-for="(candidate, index) in report.extraction.candidates" :key="index" class="candidate-result"><span class="candidate-caption">候选 {{ index + 1 }} · 对应上方高亮</span><div class="extraction-mapping"><blockquote>{{ candidate.content }}</blockquote><span aria-hidden="true">→</span><div><strong>{{ candidate.memory_value || '未指定取值' }}</strong><small>{{ types[candidate.memory_type]?.label }} · {{ candidate.memory_key || '未指定主题键' }}</small></div></div><dl class="field-grid compact-fields"><div><dt>标签</dt><dd>{{ candidate.tags.join('、') || '无' }}</dd></div><div><dt>重要性 / 置信度</dt><dd>{{ candidate.importance }} / {{ candidate.confidence }}</dd></div><div><dt>敏感信息</dt><dd>{{ candidate.sensitive ? '是，仍需明确授权' : '未被标为敏感' }}</dd></div></dl></div>
          <p v-if="!report.extraction.candidates.length" class="explanation-note">{{ report.outcome === 'privacy_blocked' ? '在提取前停止，未调用模型。' : '没有提取到可用的记忆候选。' }}</p>
          <p v-if="report.extraction.rejected_count" class="local-error">{{ report.extraction.rejected_count }} 条无有效原文依据或重复的候选已排除，不会写入。</p>
        </div>
      </article>

      <template v-if="report.traces.length">
        <template v-for="(trace, traceIndex) in report.traces" :key="traceIndex">
          <div v-if="report.traces.length > 1" class="candidate-divider">候选 {{ traceIndex + 1 }} 的实际处理 · {{ trace.result.memory?.content || '已拦截' }}</div>
          <article v-for="(step, stepIndex) in trace.steps.slice(1)" :key="step.title" class="journey-stage">
            <span class="stage-number" aria-hidden="true">{{ String(stepIndex + 3).padStart(2, '0') }}</span>
            <div class="panel stage-content"><div class="stage-heading"><h2>{{ step.title }}</h2><span class="status-tag" :class="step.status">{{ statusNames[step.status] }}</span></div><p class="step-description">{{ step.description }}</p>
              <dl v-if="step.fields.length" class="field-grid metric-fields"><div v-for="field in step.fields" :key="field.label"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd><p v-if="metricExplanation(field, trace)" class="metric-help">{{ metricExplanation(field, trace) }}</p></div></dl>

              <template v-if="stepIndex === 1">
                <div class="comparison"><div class="before-state"><span class="candidate-caption">处理前</span><template v-if="trace.previous"><p>{{ trace.previous.content }}</p><small>{{ roles[trace.previous.state_role]?.label }} · 证据 {{ trace.previous.evidence_count }} 条</small></template><p v-else>{{ step.status === 'skipped' ? '未执行比较，不能据此判断是否已有记忆。' : '本次没有读取到可比较的已有记录。' }}</p></div><div class="input-state"><span class="candidate-caption">本次输入</span><p>{{ trace.steps[0].fields[0].value }}</p><small>仅来自本次用户原话</small></div><div class="after-state"><span class="candidate-caption">处理后 · 本次涉及的记录</span><div v-for="(item, index) in afterState(trace)" :key="index" class="state-item"><span class="state-role">{{ item.role }}</span><p>{{ item.content }}</p></div><p v-if="!afterState(trace).length">本次未保存正文；不代表已有记忆为空。</p></div></div>
              </template>

              <template v-if="stepIndex === 2"><ol class="event-list"><li v-for="(event, eventIndex) in trace.events" :key="eventIndex"><span class="event-dot" /><div><strong>{{ eventNames[event.event_type] || event.event_type }}</strong><p>{{ event.message }}</p></div></li></ol><p v-if="trace.result.decision === 'CANDIDATE'" class="candidate-notice">新证据已保存为候选，但尚未同时满足数量、误差和一致性条件。原有当前记忆保留；系统不会为了走完流程而自动补充证据。</p></template>

              <template v-if="stepIndex === 3">
                <template v-if="trace.result.memory"><div class="stored-record"><div class="record-badges"><span>{{ types[trace.result.memory.memory_type]?.label }}</span><span>{{ roles[trace.result.memory.state_role]?.label }}</span></div><blockquote>{{ trace.result.memory.content }}</blockquote><dl class="field-grid"><div><dt>记忆键 / 值</dt><dd>{{ trace.result.memory.memory_key || '—' }} / {{ trace.result.memory.memory_value || '—' }}</dd></div><div><dt>证据数量</dt><dd>{{ trace.result.memory.evidence_count }}</dd></div><div><dt>记录 ID</dt><dd>{{ trace.result.memory.id }}</dd></div><div><dt>写入分数（存储值）</dt><dd>{{ trace.result.memory.write_score }}</dd></div></dl></div><p class="explanation-note">以下为本次返回的真实 SQLite 记录。强化分支可能保留已有编码分数；上面的编码环节展示本次实际计算结果。类型与状态是不同维度。</p><pre class="storage-json" aria-label="最终存储 JSON">{{ JSON.stringify(trace.result.memory, null, 2) }}</pre></template>
                <div v-else class="no-record">未保存记忆正文，仅保留原有隐私审计记录。</div>
              </template>
            </div>
          </article>
        </template>
      </template>
      <template v-else><article v-for="(title, index) in ['选择性编码', '新旧比较', '巩固决策', '存储结果']" :key="title" class="journey-stage"><span class="stage-number" aria-hidden="true">{{ String(index + 3).padStart(2, '0') }}</span><div class="panel stage-content"><div class="stage-heading"><h2>{{ title }}</h2><span class="status-tag skipped">未执行</span></div><p class="step-description">没有可用候选，本步骤未执行，没有写入记忆。</p></div></article></template>
      <p class="journey-footnote">{{ report.message }} 本页结果为提交当时的快照。</p>
    </section>
  </div>
</template>

<style scoped>
.evolution-page { max-width: 1380px; }
.evolution-label { color: var(--green); background: #edf5f0; padding: 7px 12px; border-radius: 20px; font-size: 12px; }
.input-panel { padding: 26px; }
.input-heading, .stage-heading, .journey-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.input-heading h2, .stage-heading h2 { font-size: 17px; }
.eyebrow { display: block; color: var(--muted); font-size: 11px; letter-spacing: 1px; margin-bottom: 7px; }
.user-label { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
textarea { width: 100%; border: 1px solid #e1e5ed; border-radius: 8px; padding: 14px; resize: vertical; background: #fbfcfe; color: var(--ink); font-size: 16px; line-height: 1.9; min-height: 115px; }
.submit-row { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-top: 18px; }
.submit-row p, .scope-note { color: var(--muted); font-size: 12px; line-height: 1.8; }
.submit-row .button { flex-shrink: 0; }
.scope-note { margin-top: 15px; padding-top: 14px; border-top: 1px solid var(--line); }
.processing { margin-top: 24px; padding: 28px; display: flex; gap: 16px; }
.processing p { color: var(--muted); font-size: 12px; margin-top: 10px; }
.pulse { width: 12px; height: 12px; margin-top: 6px; border-radius: 50%; background: #7397da; flex-shrink: 0; animation: pulse 1.6s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: .3; } }
@media (prefers-reduced-motion: reduce) { .pulse { animation: none; } }
.empty-evolution { text-align: center; padding: 65px 20px; color: #7f899a; }
.empty-evolution > span { display: block; font-size: 42px; color: #a3b6d2; margin-bottom: 16px; }
.empty-evolution p { margin-top: 13px; }
.empty-evolution small { display: block; margin-top: 14px; font-size: 12px; }
.journey { margin-top: 32px; }
.outcome-summary { padding: 22px 25px; margin-bottom: 24px; border-left: 3px solid #80a18f; background: #f6faf7; }
.outcome-summary h2 { font-size: 17px; line-height: 1.8; font-weight: 550; }
.summary-meta { display: flex; flex-wrap: wrap; gap: 8px 20px; margin-top: 12px; color: #7b8b82; font-size: 11px; }
.summary-list { margin: 12px 0 0; padding-left: 18px; color: #62736a; font-size: 13px; line-height: 1.8; }
.result-count { color: var(--muted); font-size: 12px; flex-shrink: 0; }
.journey-stage { position: relative; display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 15px; padding-bottom: 22px; }
.journey-stage::before { content: ''; position: absolute; left: 20px; top: 38px; bottom: -1px; width: 1px; background: #dce4ef; }
.journey-stage:last-of-type::before { display: none; }
.stage-number { position: relative; z-index: 1; display: grid; place-items: center; height: 40px; width: 40px; border: 1px solid #d9e4f4; border-radius: 50%; background: #f0f4fc; color: #7090c2; font-size: 12px; font-weight: 600; }
.stage-content { padding: 20px 24px; min-width: 0; }
.status-tag { font-size: 11px; border-radius: 5px; background: #eff3fa; color: #637b9c; padding: 4px 8px; flex-shrink: 0; }
.status-tag.done { background: #eef6f1; color: #598a70; }
.status-tag.blocked { background: #fbefed; color: #b56d5c; }
.status-tag.skipped { background: #f2f2f2; color: #8b8b8b; }
.step-description { line-height: 1.8; color: #626e81; margin-bottom: 16px; }
blockquote { margin: 0; font-size: 18px; font-weight: 500; line-height: 1.8; overflow-wrap: anywhere; }
.candidate-result { padding-top: 18px; border-top: 1px solid var(--line); margin-top: 18px; }
.candidate-caption { color: var(--muted); font-size: 11px; }
.candidate-result blockquote { font-size: 16px; margin: 9px 0 15px; }
.evidence-input mark { background: #e8f0fc; color: #325c91; border-radius: 3px; box-decoration-break: clone; }
.extraction-mapping { display: grid; grid-template-columns: minmax(0, 1fr) 20px minmax(0, 1fr); gap: 16px; align-items: center; margin: 10px 0; }
.extraction-mapping > span { color: #90a6c4; }
.extraction-mapping strong { font-size: 19px; font-weight: 550; color: #5277a3; overflow-wrap: anywhere; }
.extraction-mapping small { display: block; color: var(--muted); font-size: 11px; margin-top: 6px; overflow-wrap: anywhere; }
.field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 28px; margin: 0; }
.field-grid > div { padding: 12px 0; border-bottom: 1px solid #f0f2f5; }
.compact-fields, .metric-fields { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0 22px; }
.compact-fields > div { padding: 8px 0; }
.metric-fields dd { font-size: 18px; font-variant-numeric: tabular-nums; }
.metric-help { color: #8892a0; font-size: 11px; line-height: 1.7; margin-top: 7px; }
dt { color: var(--muted); font-size: 12px; }
dd { margin: 6px 0 0; overflow-wrap: anywhere; font-size: 14px; }
.comparison { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; margin-top: 20px; background: #f8fafc; border-radius: 8px; padding: 18px; }
.comparison > div + div { border-left: 1px solid #e3e9f2; padding-left: 18px; }
.state-role { display: inline-block; font-size: 10px; padding: 2px 6px; border-radius: 4px; background: #eaf1fa; color: #6684ac; }
.state-item { margin-top: 12px; }
.state-item + .state-item { padding-top: 10px; border-top: 1px dashed #dbe3ee; }
.comparison p { margin: 10px 0; overflow-wrap: anywhere; }
.comparison small { color: var(--muted); font-size: 11px; }
.compare-arrow { align-self: center; color: #94a9c6; font-size: 20px; }
.event-list { list-style: none; padding: 0; margin: 18px 0 0; border-top: 1px solid var(--line); }
.event-list li { display: flex; gap: 12px; padding-top: 16px; }
.event-dot { width: 8px; height: 8px; border-radius: 50%; background: #8da9ce; flex-shrink: 0; margin-top: 6px; }
.event-list strong { font-size: 13px; font-weight: 500; }
.event-list p { color: #7e8797; font-size: 12px; line-height: 1.8; margin-top: 6px; }
.candidate-notice { background: #fff9ed; color: #a38248; padding: 14px; border-radius: 7px; font-size: 12px; line-height: 1.8; margin-top: 18px; }
.record-badges { display: flex; gap: 8px; margin-bottom: 13px; }
.record-badges span { font-size: 11px; border-radius: 5px; background: #edf3fc; color: #6382ad; padding: 4px 8px; }
.stored-record blockquote { margin-bottom: 15px; }
.explanation-note, .journey-footnote { color: var(--muted); font-size: 12px; line-height: 1.8; margin-top: 14px; overflow-wrap: anywhere; }
.storage-json { margin: 18px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; background: #f7f9fc; border: 1px solid #edf0f5; padding: 18px; border-radius: 8px; font-size: 12px; line-height: 1.8; }
.no-record { background: #f9f4f2; padding: 18px; border-radius: 7px; color: #a17c6d; }
.candidate-divider { margin: 8px 0 20px 57px; font-size: 13px; color: var(--blue); overflow-wrap: anywhere; }
.local-error { color: #b35b4c; margin-top: 15px; font-size: 13px; }
@media (max-width: 900px) { .comparison { grid-template-columns: 1fr; } .comparison > div + div { border-left: 0; border-top: 1px solid #e3e9f2; padding: 14px 0 0; } .metric-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 700px) { .evolution-label { display: none; } .input-panel, .stage-content, .outcome-summary { padding: 18px; } .input-heading, .stage-heading, .journey-heading, .submit-row { flex-wrap: wrap; } .journey-stage { grid-template-columns: 30px minmax(0, 1fr); gap: 10px; } .stage-number { width: 30px; height: 30px; font-size: 10px; } .journey-stage::before { left: 14px; top: 30px; } .field-grid { grid-template-columns: 1fr; } .extraction-mapping { grid-template-columns: 1fr; gap: 4px; } .extraction-mapping > span { transform: rotate(90deg); justify-self: center; } .candidate-divider { margin-left: 40px; } }
</style>
