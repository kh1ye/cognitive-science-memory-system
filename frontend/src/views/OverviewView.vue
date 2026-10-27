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
import { moduleState, recentChange } from "../lib/overview";
const { state, refresh } = useWorkspace();
const overview = computed(() => state.overview);
const snapshot = computed(() => {
  if (!overview.value) return state.loading ? "正在读取你的记忆空间…" : "暂未取得记忆数据，请刷新重试。";
  if (overview.value.total_count === 0) return "你的记忆空间还是空的，从一句话开始观察记忆如何形成。";
  const current = overview.value.by_role.current || 0;
  const candidate = overview.value.by_role.candidate || 0;
  return `当前用户共 ${overview.value.total_count} 条记录，其中 ${current} 条为当前记忆，${candidate ? `${candidate} 条候选证据等待巩固。` : "暂无待巩固的候选证据。"}`;
});
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
  <div class="page overview-page">
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
    <section class="panel snapshot-panel" aria-label="当前近况">
      <div class="snapshot-copy"><span class="snapshot-caption">当前近况 · {{ state.user }}</span><h2>{{ snapshot }}</h2><p>{{ state.error ? '同步未成功；已有数据为上次成功同步的快照。' : state.loading ? '正在同步，已有数据为上次快照。' : '总量汇总四类记忆对象与兼容记录，包含工作状态、程序版本、历史及归档；迁移副本不重复计数。' }}</p></div>
      <div class="snapshot-actions"><RouterLink class="button primary" to="/evolution"><AppIcon name="activity" />体验记忆演化</RouterLink><RouterLink class="button" to="/memories"><AppIcon name="memory" />管理记忆</RouterLink></div>
    </section>
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
            <h2>最近变化</h2>
            <RouterLink class="text-button" to="/memories"
              >查看记忆 ↗</RouterLink
            >
          </div>
          <template v-if="overview?.recent_activity.length"
            ><div class="activity-head">
              <span>最近 {{ overview.recent_activity.length }} 项操作 · 当前用户</span><span style="text-align: right">时间</span>
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
                  <p class="change-explanation">{{ recentChange(event) }}</p>
                  <div v-if="event.related_memory && event.event_type !== 'USER_DELETE'" class="related-record"><span>关联记忆 · 当前快照 / {{ roles[event.related_memory.state_role]?.label || event.related_memory.state_role }}</span><blockquote>{{ event.related_memory.content }}</blockquote></div>
                  <small v-else-if="event.memory_id" class="missing-record">{{ event.event_type === 'USER_DELETE' || event.related_memory === null ? '关联正文已删除或不可用，仅展示操作。' : '尚未提供关联正文；升级后端后可查看。' }}</small>
                </div>
              </div>
              <time
                :datetime="event.created_at"
                :title="formatDate(event.created_at)"
                >{{ age(event.created_at) }}</time
              >
            </div></template
          >
          <div v-else class="empty overview-empty"><p>{{ state.loading ? '正在同步当前空间…' : !overview ? '暂未取得活动数据，请刷新重试。' : '还没有活动。输入一句话，看看系统如何形成记忆。' }}</p><RouterLink v-if="overview && !state.loading" class="text-button" to="/evolution">从记忆演化开始 ↗</RouterLink></div>
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
                :class="moduleState(module).tone"
                ><span class="small-dot" />{{
                  moduleState(module).label
                }}</span
              >
            </div>
          </div>
          <p class="module-note">“已配置”仅表示读取到模型配置，不代表已验证连接；查看此页不会调用模型。</p>
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

<style scoped>
.snapshot-panel { display: flex; align-items: center; justify-content: space-between; gap: 24px; padding: 22px 24px; margin-bottom: 18px; background: #f4f8fd; border-color: #e0e9f5; }
.snapshot-copy { min-width: 0; }
.snapshot-caption { display: block; color: #7890ae; font-size: 11px; margin-bottom: 8px; overflow-wrap: anywhere; }
.snapshot-copy h2 { font-size: 16px; font-weight: 550; line-height: 1.8; }
.snapshot-copy p { font-size: 11px; color: #8b97a7; margin-top: 7px; }
.snapshot-actions { display: flex; flex-wrap: wrap; flex-shrink: 0; gap: 10px; }
.activity-content { align-items: flex-start; }
.activity-content i { flex-shrink: 0; }
.activity-content .change-explanation { white-space: normal; overflow-wrap: anywhere; line-height: 1.8; color: #7d8797; }
.related-record { margin-top: 9px; border-left: 2px solid #d8e4f4; padding-left: 10px; }
.related-record > span, .missing-record { font-size: 10px; color: #98a2b0; }
.related-record blockquote { margin: 5px 0 0; font-size: 12px; color: #63748b; line-height: 1.7; overflow-wrap: anywhere; }
.missing-record { display: block; margin-top: 7px; }
.overview-empty .text-button { margin-top: 13px; }
.module-status.configured { color: #6685b6; }
.module-status.configured .small-dot { background: #7394c5; }
.module-status.warning { color: #b08847; }
.module-status.warning .small-dot { background: #c49e60; }
.module-note { border-top: 1px solid var(--line); padding: 12px 20px; font-size: 10px; color: #97a0ae; line-height: 1.8; }
@media (max-width: 1150px) { .snapshot-panel { flex-direction: column; align-items: flex-start; gap: 16px; } }
@media (max-width: 650px) { .snapshot-panel { padding: 18px; } .snapshot-actions { width: 100%; } .activity-row { grid-template-columns: minmax(0, 1fr) 60px; gap: 8px; } }
</style>
