<script setup>
import { computed, ref, watch } from "vue";
import ArchitectureMemory from "../components/ArchitectureMemory.vue";
import AppDialog from "../components/AppDialog.vue";
import AppIcon from "../components/AppIcon.vue";
import SourceEvidence from "../components/SourceEvidence.vue";
import { useWorkspace } from "../composables/useWorkspace";
import { types, roles, formatDate } from "../lib/format";
const { state, openMemory, deleteMemory, runRetention, refresh } = useWorkspace();
const source = ref(""), since = ref(""), focus = ref(""), healthOpen = ref(false);
const selectedType = ref(""),
  query = ref(""),
  role = ref(""),
  page = ref(1),
  detail = ref(null),
  checking = ref(false),
  previewId = ref(null);
const tabs = computed(() => [
  { key: "", label: "全部记忆", count: state.overview?.total_count || 0 },
  ...Object.entries(types).map(([key, type]) => ({
    key,
    label: type.label,
    count: state.overview?.by_type[key] || 0,
  })),
]);
const sources = computed(() => [...new Set(state.memories.map(m => m.source).filter(Boolean))].sort());
const candidates = computed(() => state.memories.filter(m => m.state_role === "candidate"));
const protectedCount = computed(() => state.memories.filter(m => m.is_protected).length);
const archivedCount = computed(() => state.memories.filter(m => m.state_role === "archived").length);
const duplicateGroups = computed(() => {
  const groups = new Map();
  for (const m of state.memories.filter(m => ["current", "working"].includes(m.state_role))) {
    const key = m.content.trim().toLowerCase().replace(/\s+/g, " ");
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(m);
  }
  return [...groups.values()].filter(group => group.length > 1);
});
function relatedTo(m) {
  if (!m) return [];
  const ids = new Set([m.parent_id, ...(m.support_ids || [])]);
  return state.memories.filter(other => other.id !== m.id &&
    (ids.has(other.id) || other.parent_id === m.id ||
    (m.memory_key && other.memory_key === m.memory_key)));
}
const related = computed(() => relatedTo(previewMemory.value));
const detailRelated = computed(() => relatedTo(detail.value));
watch(() => state.inspectedRecord, record => { if (record) detail.value = record; }, { immediate: true });
function resetFilters() {
  selectedType.value = query.value = role.value = source.value = since.value = focus.value = "";
}
function showCandidates() { resetFilters(); focus.value = "candidate"; healthOpen.value = false; }
watch(() => state.user, () => { resetFilters(); detail.value = null; previewId.value = null; healthOpen.value = false; });
const filtered = computed(() =>
  state.memories.filter(
    (memory) =>
      (!selectedType.value || memory.memory_type === selectedType.value) &&
      (!source.value || memory.source === source.value) &&
      (!since.value || Date.parse(memory.updated_at) >= new Date(`${since.value}T00:00:00`).getTime()) &&
      (!focus.value || (focus.value === "protected" ? memory.is_protected : memory.state_role === focus.value)) &&
      (!role.value || memory.state_role === role.value) &&
      (!query.value.trim() ||
        [memory.content, memory.memory_key, memory.memory_value, ...memory.tags]
          .join(" ")
          .toLowerCase()
          .includes(query.value.trim().toLowerCase())),
  ),
);
const pages = computed(() =>
  Math.max(1, Math.ceil(filtered.value.length / 10)),
);
const rows = computed(() =>
  filtered.value.slice((page.value - 1) * 10, page.value * 10),
);
const previewMemory = computed(
  () =>
    rows.value.find((memory) => memory.id === previewId.value) ||
    rows.value[0] ||
    null,
);
function selectMemory(memory) {
  previewId.value = memory.id;
  if (!window.matchMedia("(min-width: 1280px)").matches) detail.value = memory;
}
watch([selectedType, query, role, source, since, focus], () => {
  page.value = 1;
});
watch(pages, (value) => {
  page.value = Math.min(page.value, value);
});
const detailFields = computed(() => {
  const m = detail.value;
  if (!m) return [];
  return [
    ["类型", types[m.memory_type]?.label],
    ["状态", roles[m.state_role]?.label],
    ["主题标识", m.memory_key || "—"],
    ["主题取值", m.memory_value || "—"],
    ["证据数量", m.evidence_count],
    ["重要程度", m.importance == null ? "不适用" : Number(m.importance).toFixed(2)],
    ["写入分数", m.write_score == null ? "不适用" : Number(m.write_score).toFixed(3)],
    ["对象状态", m.native_status || "—"],
    ["是否受保护", m.is_protected ? "是" : "否"],
    ["创建时间", formatDate(m.created_at)],
    ["更新时间", formatDate(m.updated_at)],
    ["记录 ID", m.id],
    ["来源", m.source],
  ];
});
function remove(id) {
  detail.value = null;
  deleteMemory(id);
}
async function retention() {
  if (checking.value) return;
  checking.value = true;
  try {
    await runRetention();
  } finally {
    checking.value = false;
  }
}
function tabKey(event, index) {
  if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const next =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? tabs.value.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.value.length) %
          tabs.value.length;
  selectedType.value = tabs.value[next].key;
  event.currentTarget.parentElement.children[next].focus();
}
</script>
<template>
  <ArchitectureMemory :user="state.user" @changed="refresh" />
  <div class="page">
    <div class="page-heading">
      <div>
        <h1>记忆管理</h1>
        <p>查看记忆来源，对照候选与历史，了解每次变化。</p>
      </div>
      <div class="heading-actions">
        <button class="button" @click="healthOpen = true">记忆体检</button>
        <button class="button" :disabled="checking" @click="retention">
          <AppIcon name="refresh" />检查保留度</button
        ><button class="button primary" @click="openMemory()">
          <AppIcon name="plus" />添加记忆
        </button>
      </div>
    </div>
    <div class="memory-scope"><span>当前空间：<strong>{{ state.user }}</strong></span><span>以下筛选与体检基于已加载的 {{ state.memories.length }} 条记忆<span v-if="state.overview?.total_count > state.memories.length">，不覆盖全部记录</span></span></div>
    <div class="memory-shortcuts" aria-label="快捷筛选">
      <button class="panel memory-shortcut" :class="{ active: !focus }" @click="resetFilters"><span>全部已加载</span><strong>{{ state.memories.length }}</strong><small>浏览当前空间</small></button>
      <button class="panel memory-shortcut" :class="{ active: focus === 'candidate' }" @click="showCandidates"><span>待核实候选</span><strong>{{ candidates.length }}</strong><small>查看与已有记忆的差异</small></button>
      <button class="panel memory-shortcut" :class="{ active: focus === 'protected' }" @click="resetFilters(); focus = 'protected'"><span>受保护记忆</span><strong>{{ protectedCount }}</strong><small>保留度检查不会归档</small></button>
      <button class="panel memory-shortcut" :class="{ active: focus === 'archived' }" @click="resetFilters(); focus = 'archived'"><span>已归档</span><strong>{{ archivedCount }}</strong><small>回顾保留的旧记录</small></button>
    </div>
    <div class="memory-tabs" role="tablist" aria-label="记忆类型">
      <button
        v-for="(tab, index) in tabs"
        :key="tab.key"
        role="tab"
        class="memory-tab"
        :class="{ active: selectedType === tab.key }"
        :aria-selected="selectedType === tab.key"
        :tabindex="selectedType === tab.key ? 0 : -1"
        @click="selectedType = tab.key"
        @keydown="tabKey($event, index)"
      >
        {{ tab.label }}<span>{{ tab.count }}</span>
      </button>
    </div>
    <div class="memory-layout">
      <section class="panel memory-panel">
        <div class="memory-toolbar">
          <label class="search-input"
            ><AppIcon name="search" /><input
              v-model="query"
              placeholder="搜索内容、标签或主题"
              aria-label="搜索记忆" /></label
          ><select v-model="role" aria-label="筛选状态">
            <option value="">全部状态</option>
            <option v-for="(item, key) in roles" :key="key" :value="key">
              {{ item.label }}
            </option></select
          ><span class="subtle">{{ filtered.length }} 条记录</span>
        </div>
        <div class="memory-extra-filters">
          <label>来源<select v-model="source" aria-label="筛选来源"><option value="">全部来源</option><option v-for="item in sources" :key="item" :value="item">{{ item }}</option></select></label>
          <label>更新起始日期<input v-model="since" type="date" aria-label="更新起始日期" /></label>
          <span v-if="focus" class="badge">{{ focus === 'protected' ? '受保护记忆' : roles[focus]?.label }}</span>
          <button class="button small" @click="resetFilters">重置筛选</button>
        </div>
        <div class="table-scroll">
          <table class="memory-table">
            <thead>
              <tr>
                <th>记忆内容</th>
                <th>类型</th>
                <th>状态</th>
                <th>证据</th>
                <th>更新时间</th>
                <th />
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="memory in rows"
                :key="memory.id"
                :class="{ 'selected-row': previewMemory?.id === memory.id }"
              >
                <td>
                  <button class="memory-content" @click="selectMemory(memory)">
                    {{
                      memory.content.length > 90
                        ? memory.content.slice(0, 90) + "…"
                        : memory.content
                    }}
                  </button>
                  <div class="memory-tags">
                    {{
                      memory.tags.length
                        ? memory.tags.map((tag) => "#" + tag).join("  ")
                        : memory.memory_key || "无标签"
                    }}
                  </div>
                </td>
                <td>
                  {{ types[memory.memory_type]?.label || memory.memory_type }}
                </td>
                <td>
                  <span class="badge" :class="memory.state_role">{{
                    roles[memory.state_role]?.label || memory.state_role
                  }}</span>
                </td>
                <td>{{ memory.evidence_count }}</td>
                <td>{{ formatDate(memory.updated_at) }}</td>
                <td>
                  <button
                    v-if="memory.can_delete !== false"
                    class="icon-button"
                    aria-label="删除记忆"
                    @click="remove(memory.id)"
                  >
                    <AppIcon name="trash" />
                  </button>
                </td>
              </tr>
              <tr v-if="!rows.length">
                <td colspan="6">
                  <div class="empty">
                    {{
                      state.loading
                        ? "正在同步当前空间…"
                        : state.memories.length
                          ? "没有符合条件的记忆，试试其他筛选条件。"
                          : "还没有记忆，点击右上角添加。"
                    }}
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="table-footer">
          <span
            >第 {{ page }} / {{ pages }} 页 ·
            <template v-if="state.overview?.total_count > state.memories.length"
              >仅加载最近 {{ state.memories.length }} 条，共
              {{ state.overview.total_count }} 条</template
            ><template v-else>共 {{ filtered.length }} 条</template></span
          >
          <div>
            <button
              class="button small"
              :disabled="page <= 1"
              aria-label="上一页"
              @click="page--"
            >
              ←</button
            ><button
              class="button small"
              :disabled="page >= pages"
              aria-label="下一页"
              @click="page++"
            >
              →
            </button>
          </div>
        </div>
      </section>
      <aside class="panel memory-preview" aria-label="记忆预览">
        <div class="panel-heading">
          <h2>记忆预览</h2>
          <span class="subtle">选中记录</span>
        </div>
        <template v-if="previewMemory">
          <div class="preview-body">
            <div class="preview-badges">
              <span class="badge">{{
                types[previewMemory.memory_type]?.label
              }}</span
              ><span class="badge" :class="previewMemory.state_role">{{
                roles[previewMemory.state_role]?.label
              }}</span>
            </div>
            <p class="preview-content">{{ previewMemory.content }}</p>
            <div class="detail-tags">
              <span v-for="tag in previewMemory.tags" :key="tag" class="badge"
                >#{{ tag }}</span
              >
            </div>
            <dl class="preview-fields">
              <dt>来源</dt><dd>{{ previewMemory.source || "未记录" }}</dd>
              <dt>最近访问</dt><dd>{{ previewMemory.last_accessed_at ? formatDate(previewMemory.last_accessed_at) : "暂无访问记录" }}</dd>
              <dt>主题</dt>
              <dd>{{ previewMemory.memory_key || "未设置" }}</dd>
              <dt>取值</dt>
              <dd>{{ previewMemory.memory_value || "—" }}</dd>
              <dt>支持证据</dt>
              <dd>{{ previewMemory.evidence_count }} 条</dd>
              <dt>保护状态</dt>
              <dd>{{ previewMemory.is_protected ? "受保护" : "普通记忆" }}</dd>
            </dl>
            <div v-if="previewMemory.importance != null" class="preview-score">
              <div>
                <span>重要程度</span
                ><b>{{ Math.round(previewMemory.importance * 100) }}%</b>
              </div>
              <div class="bar-track">
                <div
                  class="bar-fill"
                  :style="{
                    width: `${previewMemory.importance * 100}%`,
                    background: '#839bc6',
                  }"
                />
              </div>
            </div>
            <div v-if="previewMemory.storage_kind === 'typed'" class="memory-notice">此记录来自四类记忆对象。状态为 {{ previewMemory.native_status }}，请在上方任务与来源面板管理来源和程序版本。</div>
            <div v-else-if="previewMemory.state_role === 'candidate'" class="memory-notice">这是一条候选证据，尚未替代当前记忆。系统会在后续一致证据达到阈值后判断是否巩固。</div>
            <section v-if="related.length" class="memory-relations">
              <h3>关联与新旧对照</h3>
              <p class="subtle">前序版本、支持证据及同主题记录 · 已加载范围</p>
              <button v-for="item in related" :key="item.id" class="related-memory" @click="detail = item">
                <span class="badge" :class="item.state_role">{{ roles[item.state_role]?.label }}</span>
                <small>{{ previewMemory.parent_id === item.id ? '前序记忆' : (previewMemory.support_ids || []).includes(item.id) ? '支持证据' : '同主题 / 后续记录' }}</small>
                <p>{{ item.content }}</p>
              </button>
            </section>
            <div class="preview-updated">
              更新于 {{ formatDate(previewMemory.updated_at) }}
            </div>
            <button class="button full" @click="detail = previewMemory">
              查看完整详情 <AppIcon name="external" />
            </button>
          </div>
        </template>
        <div v-else class="empty">选择一条记忆，查看其内容与来源。</div>
      </aside>
    </div>
  </div>
  <AppDialog :open="healthOpen" title="记忆体检" @update:open="healthOpen = false">
    <p class="form-hint">仅分析当前空间已加载的 {{ state.memories.length }} 条记录，不调用模型，不修改记忆。重复检查仅比较当前与工作层记录的相同正文，不代表语义去重。</p>
    <div class="health-item"><h3>待核实候选 · {{ candidates.length }} 条</h3><p>候选尚未成为当前事实，可对照已有记忆和证据来源。</p><button class="button" :disabled="!candidates.length" @click="showCandidates">查看候选</button></div>
    <div class="health-item"><h3>相同正文 · {{ duplicateGroups.length }} 组</h3><p v-if="!duplicateGroups.length">已加载的当前与工作层记录未发现相同正文。</p>
      <button v-for="group in duplicateGroups" :key="group[0].id" class="related-memory" @click="healthOpen = false; detail = group[0]"><p>{{ group[0].content }}</p><small>{{ group.length }} 条记录 · 查看详情后判断是否需要保留</small></button>
    </div>
    <div class="dialog-actions"><button class="button" @click="healthOpen = false">关闭</button></div>
  </AppDialog>
  <AppDialog :open="!!detail" title="记忆详情" @update:open="detail = null"
    ><template v-if="detail"
      ><p class="detail-content">{{ detail.content }}</p>
      <div class="detail-tags">
        <span v-for="tag in detail.tags" :key="tag" class="badge">{{
          tag
        }}</span>
      </div>
      <dl class="detail-fields">
        <template v-for="[label, value] in detailFields" :key="label"
          ><dt>{{ label }}</dt>
          <dd>{{ value }}</dd></template
        >
      </dl>
      <SourceEvidence :memory-id="detail.id" :user-id="state.user" />
      <section v-if="detailRelated.length" class="memory-relations">
        <h3>关联与新旧对照</h3><p class="subtle">当前空间已加载的关联记录</p>
        <button v-for="item in detailRelated" :key="item.id" class="related-memory" @click="detail = item">
          <span class="badge" :class="item.state_role">{{ roles[item.state_role]?.label }}</span><p>{{ item.content }}</p>
        </button>
      </section>
      <p v-if="(detail.support_ids || []).length" class="form-hint">
        此记录由 {{ (detail.support_ids || []).length }} 条候选证据巩固而来。
      </p>
      <div class="dialog-actions">
        <button v-if="detail.can_delete !== false" class="button danger" @click="remove(detail.id)">
          删除记忆</button
        ><button class="button" @click="detail = null">关闭</button>
      </div></template
    ></AppDialog
  >
</template>
