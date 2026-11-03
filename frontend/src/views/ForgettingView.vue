<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import AppIcon from '../components/AppIcon.vue';
import { useWorkspace } from '../composables/useWorkspace';
import { api } from '../lib/api';
import { types, formatDate } from '../lib/format';

const { state, notify, runRetention, openMemory } = useWorkspace();
const data = ref(null), loading = ref(true), saving = ref(false), archiving = ref(false), error = ref('');
const selectedId = ref(''), query = ref(''), kind = ref(''), horizon = ref(90), day = ref(0), page = ref(1);
let version = 0;
const enabled = computed(() => data.value?.enabled === true);
const items = computed(() => data.value?.items || []);
const selected = computed(() => items.value.find(m => m.id === selectedId.value) || items.value[0] || null);
const filtered = computed(() => items.value.filter(m => (!kind.value || m.memory_type === kind.value) &&
  (!query.value.trim() || m.content.toLowerCase().includes(query.value.trim().toLowerCase()))));
const pages = computed(() => Math.max(1, Math.ceil(filtered.value.length / 6)));
const rows = computed(() => filtered.value.slice((page.value - 1) * 6, page.value * 6));
const percent = n => n == null ? '—' : `${(Number(n) * 100).toFixed(1)}%`;
const decimal = n => Number(n || 0).toFixed(1);
const retained = (t, stability) => stability > 0 ? Math.exp(-t / stability) : 0;
const x = t => 54 + Math.min(horizon.value, Math.max(0, t)) / horizon.value * 666;
const y = r => 28 + (1 - r) * 208;
function path(stability) {
  return Array.from({ length: 181 }, (_, i) => {
    const t = i / 180 * horizon.value;
    return `${i ? 'L' : 'M'}${x(t).toFixed(2)},${y(retained(t, stability)).toFixed(2)}`;
  }).join(' ');
}
const curve = computed(() => selected.value ? path(selected.value.stability_days) : '');
const baseline = computed(() => selected.value ? path(selected.value.initial_stability_days) : '');
const inspectedRetention = computed(() => selected.value ? retained(day.value, selected.value.stability_days) : null);
const archiveLine = computed(() => selected.value?.write_score > 0 ? Math.min(1, data.value.threshold / selected.value.write_score) : 1);

async function load() {
  if (saving.value) return;
  const current = ++version, user = state.user;
  loading.value = true;
  error.value = '';
  try {
    const response = await api(`/api/retention?user_id=${encodeURIComponent(user)}&limit=1000`);
    if (current !== version || user !== state.user) return;
    data.value = response;
    if (!response.items.some(m => m.id === selectedId.value)) {
      const reinforced = response.items.find(m => m.stability_days > m.initial_stability_days * 1.01);
      selectedId.value = (reinforced || response.items[0])?.id || '';
    }
  } catch (e) {
    if (current === version) { error.value = e.message; data.value = null; }
  } finally {
    if (current === version) loading.value = false;
  }
}
async function toggle() {
  if (saving.value || !data.value || loading.value) return;
  const user = state.user;
  saving.value = true;
  try {
    const response = await api('/api/retention/settings', { method: 'PUT', body: JSON.stringify({ user_id: user, enabled: !enabled.value }) });
    if (user !== state.user) return;
    data.value.enabled = response.enabled;
    notify(response.enabled ? '记忆遗忘已开启' : '记忆遗忘已关闭');
  } catch (e) { if (user === state.user) notify(`设置未保存：${e.message}`); }
  finally { saving.value = false; }
}
async function archive() {
  archiving.value = true;
  try { await runRetention(); await load(); }
  finally { archiving.value = false; }
}
function inspect(event) {
  const rect = event.currentTarget.getBoundingClientRect();
  if (rect.width) day.value = Math.round(Math.max(0, Math.min(1, ((event.clientX - rect.left) / rect.width * 760 - 54) / 666)) * horizon.value);
}
watch([query, kind], () => { page.value = 1; });
watch(pages, n => { page.value = Math.min(page.value, n); });
watch(selected, m => { day.value = Math.min(horizon.value, Math.round(m?.elapsed_days || 0)); });
watch(horizon, n => { day.value = Math.min(day.value, n); });
watch(() => [state.user, state.updatedAt], load, { immediate: true });
onMounted(() => window.addEventListener('focus', load));
onBeforeUnmount(() => { ++version; window.removeEventListener('focus', load); });
</script>

<template>
  <div class="forget-page">
    <header class="forget-heading">
      <div><span class="forget-eyebrow"><AppIcon name="brain" /> COGNITIVE RETENTION</span><h1>记忆遗忘</h1></div>
      <button class="forget-refresh" :disabled="loading || saving" @click="load"><AppIcon name="refresh" />{{ loading ? '同步中' : '同步记忆' }}</button>
    </header>

    <section class="forget-hero">
      <div class="forget-intro">
        <div class="forget-kicker"><span />有选择地遗忘，有意义地记住</div>
        <h2>让重要的记忆，<br /><em>留得更久。</em></h2>
        <div class="forget-philosophy"><p>记忆不应无限累积，而应有选择地遗忘。</p><p>冗余召回可能造成<span>上下文膨胀</span>与 <span>Token 消耗激增</span>。</p></div>
        <div class="forget-hero-stats">
          <div><span>纳入评估</span><strong>{{ data?.summary.total ?? '—' }}<small> 条</small></strong></div>
          <div><span>重要记忆保护</span><strong>{{ data?.summary.protected ?? '—' }}<small> 条</small></strong></div>
          <div><span>平均保持度</span><strong>{{ percent(data?.summary.average_retention) }}</strong></div>
        </div>
      </div>
      <div class="forget-brain-scene" aria-hidden="true">
        <svg viewBox="0 0 440 290" class="forget-brain-art">
          <defs>
            <radialGradient id="brain-aura"><stop stop-color="#7961ca" stop-opacity=".25"/><stop offset="1" stop-color="#7961ca" stop-opacity="0"/></radialGradient>
            <linearGradient id="brain-fill" x1="0" x2="1" y2="1"><stop stop-color="#28243f"/><stop offset="1" stop-color="#161c27"/></linearGradient>
            <linearGradient id="brain-stroke" x1="0" x2="1" y2="1"><stop stop-color="#c8affc"/><stop offset=".5" stop-color="#a29cda"/><stop offset="1" stop-color="#86d8c0"/></linearGradient>
            <filter id="brain-glow"><feGaussianBlur stdDeviation="3"/></filter>
          </defs>
          <ellipse cx="223" cy="151" rx="185" ry="138" fill="url(#brain-aura)"/>
          <g fill="none" stroke="#807298" stroke-width=".7">
            <ellipse cx="223" cy="152" rx="178" ry="71" transform="rotate(-18 223 152)" opacity=".35"/>
            <ellipse cx="223" cy="152" rx="157" ry="104" transform="rotate(25 223 152)" opacity=".2"/>
            <circle cx="223" cy="151" r="123" stroke-dasharray="2 9" opacity=".3"/>
          </g>
          <g class="forget-brain-body" fill="url(#brain-fill)" stroke="url(#brain-stroke)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M218 77c-8-28-44-27-53-5-25-4-43 16-39 39-25 7-30 38-15 55-7 21 5 45 28 48 10 25 40 30 57 13 13 4 22-4 22-17V77Z"/>
            <path d="M228 77c8-28 44-27 53-5 25-4 43 16 39 39 25 7 30 38 15 55 7 21-5 45-28 48-10 25-40 30-57 13-13 4-22-4-22-17V77Z"/>
            <g fill="none" opacity=".85"><path d="M165 72c-5 18 0 31 17 36m-56 3c9-7 22-5 28 5 5 9 1 20-7 25m-36 25c14-6 30-2 32 12m-4 36c15-6 21-21 14-32m65-47c-25 6-34-12-36-27m-28 8c15-2 32 9 31 26m-33 15c6 17 28 21 42 9m-13 59c-6-12-2-25 10-31m91-122c5 18 0 31-17 36m56 3c-9-7-22-5-28 5-5 9-1 20 7 25m36 25c-14-6-30-2-32 12m4 36c-15-6-21-21-14-32m-65-47c25 6 34-12 36-27m28 8c-15-2-32 9-31 26m33 15c-6 17-28 21-42 9m13 59c6-12 2-25-10-31"/></g>
          </g>
          <g fill="#b8a1ed" class="forget-neurons"><circle cx="182" cy="108" r="3.5"/><circle cx="154" cy="157" r="3"/><circle cx="194" cy="166" r="3"/><circle cx="264" cy="108" r="3.5"/><circle cx="292" cy="157" r="3"/><circle cx="252" cy="166" r="3"/></g>
          <g fill="#a1e1cb"><circle cx="70" cy="181" r="3"/><circle cx="376" cy="111" r="3"/><circle cx="300" cy="42" r="2"/></g>
          <g fill="#8e849e" font-size="9" letter-spacing="2"><text x="40" y="104">ENCODE</text><text x="330" y="213">REINFORCE</text></g>
        </svg>
        <span class="forget-brain-caption">时间 × 稳定性 × 真实证据</span>
      </div>
      <div class="forget-control" :class="{ paused: !enabled }">
        <div class="forget-control-icon"><AppIcon name="brain" /></div>
        <div class="forget-control-copy"><strong>记忆遗忘 <span>{{ !data ? loading ? '读取中' : '未读取' : enabled ? '已开启' : '已关闭' }}</span></strong><p>{{ !data ? '读取后可管理当前空间的记忆遗忘策略。' : enabled ? '应用时间衰减，适度调整检索优先级。' : '不应用衰减影响，重新开启时按实际时间计算。' }}</p></div>
        <button class="forget-switch" role="switch" :aria-checked="enabled" aria-label="记忆遗忘" :disabled="saving || loading || !data" @click="toggle"><span /></button>
      </div>
    </section>

    <div v-if="error" class="forget-error" role="alert">暂时无法读取遗忘数据：{{ error }}<button @click="load">重新加载</button></div>

    <section class="forget-analysis">
      <div class="forget-chart-panel">
        <div class="forget-panel-top"><div><span class="forget-section-index">01 / RETENTION</span><h2>艾宾浩斯遗忘曲线</h2></div><div class="forget-period" aria-label="曲线时间范围"><button v-for="n in [30, 90, 180, 365]" :key="n" :aria-pressed="horizon === n" @click="horizon = n">{{ n }} 天</button></div></div>
        <div class="forget-chart-meta"><div class="forget-chart-legend"><span><i />当前记忆</span><span><i class="baseline" />单次编码参考</span></div><code>R(t) = e<sup>−t / S</sup></code></div>
        <div class="forget-chart-wrap">
          <svg viewBox="0 0 760 282" role="img" :aria-label="selected ? `记忆遗忘曲线，稳定性 ${decimal(selected.stability_days)} 天` : '暂无记忆可绘制遗忘曲线'" @pointermove="inspect">
            <defs><linearGradient id="retention-area" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#9bd9bf" stop-opacity=".16"/><stop offset="1" stop-color="#9bd9bf" stop-opacity="0"/></linearGradient></defs>
            <g v-for="tick in [1, .75, .5, .25, 0]" :key="tick" class="forget-grid"><line x1="54" x2="720" :y1="y(tick)" :y2="y(tick)"/><text x="40" :y="y(tick) + 4" text-anchor="end">{{ tick * 100 }}%</text></g>
            <g v-for="tick in [0, 1, 2, 3, 4, 5, 6]" :key="tick" class="forget-grid"><text :x="x(tick * horizon / 6)" y="260" text-anchor="middle">{{ Math.round(tick * horizon / 6) }} 天</text></g>
            <template v-if="selected">
              <path :d="`${curve} L720,236 L54,236 Z`" fill="url(#retention-area)"/>
              <line x1="54" x2="720" :y1="y(archiveLine)" :y2="y(archiveLine)" class="forget-threshold"/>
              <path :d="baseline" class="forget-baseline" data-testid="baseline-curve"/>
              <path :d="curve" class="forget-curve" data-testid="retention-curve"/>
              <line :x1="x(day)" :x2="x(day)" y1="28" y2="236" class="forget-crosshair"/>
              <circle :cx="x(day)" :cy="y(inspectedRetention)" r="8" fill="#9ddbbf" fill-opacity=".15"/><circle :cx="x(day)" :cy="y(inspectedRetention)" r="4" fill="#b3efd2" stroke="#192820" stroke-width="2"/>
            </template>
          </svg>
          <div v-if="!selected" class="forget-chart-empty"><AppIcon name="brain" /><strong>{{ loading ? '正在读取真实记忆…' : '从第一段记忆开始' }}</strong><p>保存记忆后，这里会呈现它随时间变化的真实曲线。</p><button class="button" @click="openMemory()">添加记忆</button></div>
        </div>
        <div v-if="selected" class="forget-scrubber"><span>第 <b>{{ day }}</b> 天</span><input v-model.number="day" type="range" min="0" :max="horizon" aria-label="查看指定天数的保持度" /><strong>{{ percent(inspectedRetention) }}</strong></div>
        <p class="forget-chart-note">{{ enabled ? '按真实稳定性计算' : '当前为理论曲线 · 遗忘已关闭' }}<span>虚线为单次编码参考 · 水平线为归档阈值参考</span></p>
      </div>

      <aside class="forget-inspector">
        <span class="forget-section-index">SELECTED MEMORY</span>
        <template v-if="selected">
          <div class="forget-inspector-tags"><span>{{ types[selected.memory_type]?.label || '记忆' }}</span><span :class="{ protected: selected.protected }">{{ selected.protected ? '重要记忆保护' : selected.archive_eligible ? '可归档' : '保持中' }}</span></div>
          <p class="forget-selected-content">{{ selected.content }}</p>
          <div class="forget-current"><span>当前自然保持度</span><strong>{{ percent(selected.retention_probability) }}</strong><small>距最近编码 / 确认 {{ decimal(selected.elapsed_days) }} 天</small></div>
          <dl><div><dt>记忆稳定性 S</dt><dd>{{ decimal(selected.stability_days) }} 天</dd></div><div><dt>支持证据</dt><dd>{{ selected.evidence_count }} 条</dd></div><div><dt>{{ selected.protected ? '保留策略' : '归档参考时间' }}</dt><dd>{{ selected.protected ? '持续保护' : selected.forget_at ? formatDate(selected.forget_at) : '不受时间衰减' }}</dd></div></dl>
          <RouterLink class="forget-detail-link" :to="{ name: 'memories', query: { record: selected.id } }">查看记忆与证据<AppIcon name="external" /></RouterLink>
        </template>
        <div v-else class="forget-inspector-empty"><AppIcon name="brain" /><p>选择一段记忆，<br />了解它的保持与强化。</p></div>
      </aside>
    </section>

    <section class="forget-records">
      <div class="forget-panel-top"><div><span class="forget-section-index">02 / MEMORY TRACES</span><h2>每段记忆，都有自己的节奏</h2></div><button class="button" :disabled="!enabled || loading || saving || archiving || !data?.summary.archive_eligible" @click="archive"><AppIcon name="layers" />{{ archiving ? '正在检查…' : '归档低价值记忆' }}</button></div>
      <div class="forget-table-tools"><label><AppIcon name="search" /><input v-model="query" placeholder="寻找一段记忆…" aria-label="搜索遗忘记忆" /></label><select v-model="kind" aria-label="筛选遗忘记忆类型"><option value="">全部记忆类型</option><option v-for="(type, key) in types" :key="key" :value="key">{{ type.label }}</option></select><span>当前空间 · {{ state.user }}</span></div>
      <div class="forget-table-scroll"><table class="forget-table"><thead><tr><th>记忆内容</th><th>自然保持度</th><th>稳定性</th><th>证据</th><th>保留状态</th></tr></thead><tbody><tr v-for="m in rows" :key="m.id" :class="{ selected: selected?.id === m.id }"><td><button :aria-pressed="selected?.id === m.id" @click="selectedId = m.id"><AppIcon name="brain" /><span>{{ m.content }}<small>{{ types[m.memory_type]?.label }} · {{ formatDate(m.created_at) }}</small></span></button></td><td><div class="forget-retention-cell"><span>{{ percent(m.retention_probability) }}</span><i><b :style="{ width: `${m.retention_probability * 100}%` }" /></i></div></td><td>{{ decimal(m.stability_days) }} 天</td><td>{{ m.evidence_count }} 条</td><td><span class="forget-status" :class="{ protected: m.protected, eligible: m.archive_eligible }">{{ m.protected ? '受保护' : m.archive_eligible ? '可归档' : '保持中' }}</span></td></tr></tbody></table></div>
      <div v-if="!rows.length" class="forget-list-empty">{{ loading ? '正在同步记忆…' : items.length ? '没有找到匹配的记忆。' : '这个空间还没有可评估的记忆。' }}</div>
      <footer class="forget-table-footer"><span>{{ filtered.length }} 条已加载记录<span v-if="data?.truncated"> · 全空间共 {{ data.summary.total }} 条，仅显示前 1000 条</span> · 已归档记录请在记忆管理中查看</span><div><button :disabled="page <= 1" aria-label="上一页记忆" @click="page--">←</button><span>{{ page }} / {{ pages }}</span><button :disabled="page >= pages" aria-label="下一页记忆" @click="page++">→</button></div></footer>
    </section>
    <footer class="forget-footer"><AppIcon name="check" /><p>重要记忆持续受保护。归档保留正文与证据，不会因时间流逝被删除。</p><span>更新于 {{ data ? formatDate(data.evaluated_at) : '—' }} · 归档由你手动执行</span></footer>
  </div>
</template>

<style scoped src="./forgetting.css"></style>
