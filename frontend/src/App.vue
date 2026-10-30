<script setup>
import { computed, onMounted, onUnmounted, provide, ref, watch } from "vue";
import { useRoute } from "vue-router";
import AppIcon from "./components/AppIcon.vue";
import AppDialog from "./components/AppDialog.vue";
import MemoryForm from "./components/MemoryForm.vue";
import { createWorkspace, WorkspaceKey } from "./composables/useWorkspace";
const workspace = createWorkspace();
provide(WorkspaceKey, workspace);
const { state, refresh, initialize, switchUser, resolveConfirm, dispose } = workspace;
const route = useRoute();
const title = computed(() => route.meta.title || "系统总览");
function readSidebarPreference() {
  try {
    const saved = localStorage.getItem("cm.sidebarCollapsed");
    if (saved !== null) return saved === "true";
  } catch { /* The toggle remains available when storage is blocked. */ }
  return window.matchMedia?.("(max-width: 650px)").matches || false;
}
const sidebarCollapsed = ref(readSidebarPreference());
function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value;
  try { localStorage.setItem("cm.sidebarCollapsed", String(sidebarCollapsed.value)); } catch { /* Session-only preference. */ }
}
const profileOpen = ref(false),
  userInput = ref("");
watch(
  title,
  (value) => {
    document.title = `${value} · Cognitive Science Memory System`;
  },
  { immediate: true },
);
function openProfile() {
  userInput.value = state.user;
  profileOpen.value = true;
}
function submitProfile() {
  if (!userInput.value.trim()) return;
  switchUser(userInput.value);
  profileOpen.value = false;
}
watch(() => Boolean(route.name && !route.meta.landing), (workspaceVisible) => {
  if (workspaceVisible) initialize();
}, { immediate: true });
onUnmounted(dispose);
const memoryRoutes = new Set(["memories", "memory-gallery"]);
function syncMemories() {
  if (memoryRoutes.has(route.name) && !state.loading && document.visibilityState !== "hidden") refresh();
}
watch(() => route.name, (name, previous) => {
  if (previous && memoryRoutes.has(name)) syncMemories();
});
onMounted(() => {
  window.addEventListener("focus", syncMemories);
  document.addEventListener("visibilitychange", syncMemories);
});
onUnmounted(() => {
  window.removeEventListener("focus", syncMemories);
  document.removeEventListener("visibilitychange", syncMemories);
});
let openedSourceLink = "", openedRecordLink = "";
watch(() => [route.name, route.query.thread, route.query.message, state.sessionsLoading, state.user],
  ([name, thread, message, loading, user]) => {
    const key = name === "assistant" && typeof thread === "string" ? JSON.stringify([user, thread, message]) : "";
    if (!key) openedSourceLink = "";
    else if (!loading && key !== openedSourceLink) {
      openedSourceLink = key;
      workspace.openSourceThread(thread, typeof message === "string" ? message : "");
    }
  });
watch(() => [route.name, route.query.record, state.loading, state.user], ([name, id, loading, user]) => {
  const key = name === "memories" && typeof id === "string" ? JSON.stringify([user, id]) : "";
  if (!key) { openedRecordLink = ""; state.inspectedRecord = null; }
  else if (!loading && key !== openedRecordLink) {
    openedRecordLink = key;
    workspace.inspectMemory(id);
  }
});
const navigationGroups = [
  { title: "开始使用", items: [
    { path: "/", title: "产品首页", icon: "layers" },
    { name: "overview", title: "系统总览", icon: "overview" },
  ] },
  { title: "记忆工作台", items: [
    { name: "assistant", title: "个人助手", icon: "chat" },
    { name: "memories", title: "记忆管理", icon: "memory" },
    { name: "memory-gallery", title: "记忆展示", icon: "constellation" },
    { name: "evolution", title: "记忆演化", icon: "activity" },
  ] },
  { title: "开发与设置", items: [
    { name: "connections", title: "接入管理", icon: "database" },
    { name: "install", title: "安装与接入", icon: "layers" },
    { href: "/docs", title: "接口文档", icon: "book" },
  ] },
];
</script>
<template>
  <RouterView v-if="route.meta.landing" />
  <div v-else class="layout" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <aside id="workspace-sidebar" class="sidebar">
      <RouterLink class="brand sidebar-link" to="/overview" aria-label="记忆工作台首页" :data-tooltip="sidebarCollapsed ? '记忆工作台首页' : null"
        ><span class="brand-mark">m<span /></span
        ><span class="brand-copy brand-name">Cognitive Science<br />Memory System</span></RouterLink
      >
      <nav aria-label="主导航" class="grouped-navigation">
        <section v-for="group in navigationGroups" :key="group.title" class="nav-group" :aria-label="group.title">
          <div class="nav-label nav-group-label">{{ group.title }}</div>
          <template v-for="item in group.items" :key="item.title">
            <a v-if="item.href" :href="item.href" target="_blank" rel="noopener" class="sidebar-link" :aria-label="`${item.title}（新窗口）`" :data-tooltip="sidebarCollapsed ? item.title : null"><AppIcon :name="item.icon" /><span class="nav-name">{{ item.title }}</span></a>
            <RouterLink v-else :to="item.path || { name: item.name }" active-class="active" class="sidebar-link" :aria-label="item.title" :data-tooltip="sidebarCollapsed ? item.title : null"><AppIcon :name="item.icon" /><span class="nav-name">{{ item.title }}</span><span v-if="item.name === 'memories'" class="nav-count">{{ state.overview?.total_count ?? "—" }}</span></RouterLink>
          </template>
        </section>
      </nav>
      <div class="sidebar-note">
        <span class="small-dot" />本地记忆空间
        <p>保留重要的事，让每次对话有迹可循。</p>
      </div>
      <div class="sidebar-bottom">
        <button class="profile sidebar-link" :aria-label="`切换用户空间：${state.user}`" :data-tooltip="sidebarCollapsed ? `切换用户空间：${state.user}` : null" :disabled="state.sending" @click="openProfile">
          <span class="avatar">U</span
          ><span
            ><b>{{ state.user }}</b
            ><small>个人工作空间</small></span
          ><AppIcon name="chevron" />
        </button>
      </div>
    </aside>
    <main>
      <header class="topbar">
        <div class="topbar-leading">
          <button class="icon-button sidebar-toggle" :aria-label="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'" :title="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'" :aria-expanded="!sidebarCollapsed" aria-controls="workspace-sidebar" @click="toggleSidebar"><AppIcon name="sidebar" /></button>
          <div class="breadcrumb">工作空间 <span>/</span><b>{{ title }}</b></div>
        </div>
        <div class="connection">
          <span
            class="small-dot"
            :style="{ background: state.connected ? '#84a18d' : '#c79383' }"
          /><span>{{
            state.connected
              ? "本地服务已连接"
              : state.loading
                ? "连接中"
                : "连接异常"
          }}</span>
        </div>
      </header>
      <RouterView :key="state.user" />
      <div v-if="state.error" class="load-error" role="alert">
        {{ state.error }}
        <button class="text-button" :disabled="state.loading" @click="refresh">
          刷新
        </button>
      </div>
    </main>
  </div>
  <MemoryForm />
  <AppDialog v-model:open="profileOpen" title="切换用户空间"
    ><form @submit.prevent="submitProfile">
      <label
        >用户 ID<input v-model="userInput" required maxlength="100"
      /></label>
      <p class="form-hint">
        记忆与会话按用户 ID 区分。这是本地空间切换，不提供身份认证。
      </p>
      <div class="dialog-actions">
        <button type="button" class="button" @click="profileOpen = false">
          取消</button
        ><button class="button primary" :disabled="state.sending">
          切换空间
        </button>
      </div>
    </form></AppDialog
  >
  <AppDialog
    :open="!!state.confirm"
    :title="state.confirm?.title || '确认操作'"
    @update:open="resolveConfirm(false)"
    ><template v-if="state.confirm"
      ><p class="confirm-text">{{ state.confirm.text }}</p>
      <div class="dialog-actions">
        <button class="button" @click="resolveConfirm(false)">取消</button
        ><button class="button danger" @click="resolveConfirm(true)">
          {{ state.confirm.action }}
        </button>
      </div></template
    ></AppDialog
  >
  <div v-if="state.toast" class="toast" role="status">{{ state.toast }}</div>
</template>
