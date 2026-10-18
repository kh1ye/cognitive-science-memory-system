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
const profileOpen = ref(false),
  userInput = ref("");
watch(
  title,
  (value) => {
    document.title = `${value} · Cognitive Memory System`;
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
onMounted(initialize);
onUnmounted(dispose);
const navigation = [
  { name: "overview", title: "系统总览", icon: "overview" },
  { name: "assistant", title: "个人助手", icon: "chat" },
  { name: "memories", title: "记忆管理", icon: "memory" },
];
</script>
<template>
  <div class="layout">
    <aside class="sidebar">
      <RouterLink class="brand" to="/overview"
        ><span class="brand-mark">m<span /></span
        ><span>记忆工作台<small>Cognitive Memory System</small></span></RouterLink
      >
      <div class="nav-label">工作空间</div>
      <nav aria-label="主导航">
        <RouterLink
          v-for="item in navigation"
          :key="item.name"
          :to="{ name: item.name }"
          active-class="active"
          ><AppIcon :name="item.icon" />{{ item.title
          }}<span v-if="item.name === 'memories'">{{
            state.overview?.total_count ?? "—"
          }}</span></RouterLink
        >
      </nav>
      <div class="sidebar-note">
        <span class="small-dot" />本地记忆空间
        <p>保留重要的事，让每次对话有迹可循。</p>
      </div>
      <div class="sidebar-bottom">
        <a href="/docs" target="_blank" rel="noopener"
          ><AppIcon name="book" />接口文档<AppIcon name="external" /></a
        ><button class="profile" :disabled="state.sending" @click="openProfile">
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
        <div class="breadcrumb">
          工作空间 <span>/</span><b>{{ title }}</b>
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
