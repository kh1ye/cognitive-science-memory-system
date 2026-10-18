<script setup>
import { computed, ref, watch } from "vue";
import AppDialog from "../components/AppDialog.vue";
import AppIcon from "../components/AppIcon.vue";
import { useWorkspace } from "../composables/useWorkspace";
import { types, roles, formatDate } from "../lib/format";
const { state, openMemory, deleteMemory, runRetention } = useWorkspace();
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
const filtered = computed(() =>
  state.memories.filter(
    (memory) =>
      (!selectedType.value || memory.memory_type === selectedType.value) &&
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
watch([selectedType, query, role], () => {
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
    ["重要程度", Number(m.importance).toFixed(2)],
    ["写入分数", Number(m.write_score).toFixed(3)],
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
  <div class="page">
    <div class="page-heading">
      <div>
        <h1>记忆管理</h1>
        <p>查看被记住的内容，保留、回顾或移除。</p>
      </div>
      <div class="heading-actions">
        <button class="button" :disabled="checking" @click="retention">
          <AppIcon name="refresh" />检查保留度</button
        ><button class="button primary" @click="openMemory()">
          <AppIcon name="plus" />添加记忆
        </button>
      </div>
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
              <dt>主题</dt>
              <dd>{{ previewMemory.memory_key || "未设置" }}</dd>
              <dt>取值</dt>
              <dd>{{ previewMemory.memory_value || "—" }}</dd>
              <dt>支持证据</dt>
              <dd>{{ previewMemory.evidence_count }} 条</dd>
              <dt>保护状态</dt>
              <dd>{{ previewMemory.is_protected ? "受保护" : "普通记忆" }}</dd>
            </dl>
            <div class="preview-score">
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
      <p v-if="detail.support_ids.length" class="form-hint">
        此记录由 {{ detail.support_ids.length }} 条候选证据巩固而来。
      </p>
      <div class="dialog-actions">
        <button class="button danger" @click="remove(detail.id)">
          删除记忆</button
        ><button class="button" @click="detail = null">关闭</button>
      </div></template
    ></AppDialog
  >
</template>
