<script setup>
import { computed } from "vue";
import { useWorkspace } from "../composables/useWorkspace";
import {
  types,
  roles,
  bytes,
  age,
  formatDate,
  eventNames,
} from "../lib/format";
import AppIcon from "../components/AppIcon.vue";
const { state, refresh } = useWorkspace();
const overview = computed(() => state.overview);
const today = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "short",
}).format(new Date());
const metrics = computed(() => [
  {
    label: "记忆总量",
    value: overview.value?.total_count ?? "—",
    icon: "memory",
    color: "blue",
    hint: "包含历史与已归档记录",
  },
  {
    label: "活跃记忆",
    value: overview.value?.active_count ?? "—",
    icon: "activity",
    color: "green",
    hint: "当前参与记忆生命周期",
  },
  {
    label: "待巩固证据",
    value: overview.value ? overview.value.by_role.candidate || 0 : "—",
    icon: "layers",
    color: "amber",
    hint: "等待更多一致证据",
  },
  {
    label: "本地存储",
    value: overview.value
      ? bytes(
          overview.value.storage.mode === "memory"
            ? overview.value.storage.allocated_bytes
            : overview.value.storage.database_bytes +
                overview.value.storage.wal_bytes,
        )
      : "—",
    icon: "database",
    color: "gray",
    hint: "数据库及日志 · 全部用户",
  },
]);
const donut = computed(() => {
  if (!overview.value?.total_count) return "#edf0f5";
  let start = 0;
  const slices = [];
  for (const [key, role] of Object.entries(roles)) {
    const count = overview.value.by_role[key] || 0,
      end = start + (count / overview.value.total_count) * 100;
    if (count) slices.push(`${role.color} ${start}% ${end}%`);
    start = end;
  }
  return `conic-gradient(${slices.join(",")})`;
});
</script>
<template>
  <div class="page">
    <div class="page-heading">
      <div>
        <h1>系统总览</h1>
        <p>你的记忆空间，近况一目了然。</p>
      </div>
      <div class="heading-actions">
        <span class="date-chip">{{ today }}</span
        ><button class="button" :disabled="state.loading" @click="refresh">
          <AppIcon name="refresh" />刷新
        </button>
      </div>
    </div>
    <div class="metrics">
      <article v-for="metric in metrics" :key="metric.label" class="metric">
        <div>
          {{ metric.label
          }}<span class="metric-icon" :class="metric.color"
            ><AppIcon :name="metric.icon"
          /></span>
        </div>
        <strong>{{ metric.value }}</strong
        ><small>{{ metric.hint }}</small>
      </article>
    </div>
    <div class="overview-grid">
      <div class="overview-column">
        <section class="panel types-panel">
          <div class="panel-heading">
            <h2>记忆类型分布</h2>
            <span class="subtle">全部记录</span>
          </div>
          <div class="type-chart">
            <div v-for="(type, key) in types" :key="key" class="type-row">
              <div class="type-label">
                <span :style="{ background: type.color }" />{{ type.label }}
              </div>
              <div
                class="bar-track"
                role="img"
                :aria-label="`${type.label} ${overview?.by_type[key] || 0} 条`"
              >
                <div
                  class="bar-fill"
                  :style="{
                    width: `${overview?.total_count ? ((overview.by_type[key] || 0) / overview.total_count) * 100 : 0}%`,
                    background: type.color,
                  }"
                />
              </div>
              <strong>{{ overview?.by_type[key] || 0 }}</strong>
            </div>
          </div>
          <div class="panel-foot">不同形式的记忆，各有其位置。</div>
        </section>
        <section class="panel activity-panel">
          <div class="panel-heading">
            <h2>最近活动</h2>
            <RouterLink class="text-button" to="/memories"
              >查看记忆 ↗</RouterLink
            >
          </div>
          <template v-if="overview?.recent_activity.length"
            ><div class="activity-head">
              <span>活动记录</span><span style="text-align: right">时间</span>
            </div>
            <div
              v-for="event in overview.recent_activity"
              :key="event.id"
              class="activity-row"
            >
              <div class="activity-content">
                <AppIcon
                  :name="
                    event.event_type === 'RETRIEVE'
                      ? 'search'
                      : event.event_type === 'USER_DELETE'
                        ? 'trash'
                        : 'layers'
                  "
                />
                <div>
                  <b>{{ eventNames[event.event_type] || event.event_type }}</b>
                  <p :title="event.message">{{ event.message }}</p>
                </div>
              </div>
              <time
                :datetime="event.created_at"
                :title="formatDate(event.created_at)"
                >{{ age(event.created_at) }}</time
              >
            </div></template
          >
          <div v-else class="empty">
            {{
              state.loading
                ? "正在同步当前空间…"
                : "还没有活动。添加第一条记忆，开始积累。"
            }}
          </div>
        </section>
      </div>
      <div class="overview-column">
        <section class="panel state-panel">
          <div class="panel-heading">
            <h2>记忆状态</h2>
            <span class="subtle">生命周期</span>
          </div>
          <div class="state-layout">
            <div
              class="donut"
              :style="{ background: donut }"
              :aria-label="`共 ${overview?.total_count || 0} 条记忆，状态详见右侧`"
            >
              <div>
                <strong>{{ overview?.total_count || 0 }}</strong
                ><small>条记忆</small>
              </div>
            </div>
            <div class="legend">
              <div v-for="(role, key) in roles" :key="key" class="legend-row">
                <span
                  class="legend-dot"
                  :style="{ background: role.color }"
                />{{ role.label
                }}<strong>{{ overview?.by_role[key] || 0 }}</strong>
              </div>
            </div>
          </div>
        </section>
        <section class="panel modules-panel">
          <div class="panel-heading">
            <h2>核心模块</h2>
            <span class="subtle">当前配置</span>
          </div>
          <div class="module-list">
            <div
              v-for="module in overview?.modules || []"
              :key="module.name"
              class="module-row"
            >
              <div>
                <b>{{ module.name }}</b
                ><small>{{ module.description }}</small>
              </div>
              <span
                class="module-status"
                :class="{ off: module.status !== 'ready' }"
                ><span class="small-dot" />{{
                  module.status === "ready" ? "已就绪" : "未接入"
                }}</span
              >
            </div>
          </div>
        </section>
      </div>
    </div>
    <footer class="overview-footer">
      <span
        >SQLite ·
        {{ overview?.storage.mode === "memory" ? "内存模式" : "本地持久化"
        }}<template v-if="overview">
          · 数据页 {{ bytes(overview.storage.allocated_bytes) }}</template
        ></span
      ><span>{{
        state.updatedAt ? `更新于 ${state.updatedAt}` : "等待同步"
      }}</span>
    </footer>
  </div>
</template>
