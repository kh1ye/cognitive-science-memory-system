<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue";
import AppDialog from "../components/AppDialog.vue";
import UserProfileView from "./UserProfileView.vue";
import WorkingMemoryPanel from "../components/WorkingMemoryPanel.vue";
import AppIcon from "../components/AppIcon.vue";
import { api } from "../lib/api";
import { conversationStyles, chatStyle } from "../lib/conversationStyles";
import { useWorkspace } from "../composables/useWorkspace";
import { types, roles, memoryStatusNames, formatMemoryDecision } from "../lib/format";
const {
  state,
  currentChat,
  newChat,
  selectChat,
  deleteChat,
  sendMessage,
  setChatPreferences,
  openMemory,
  notify,
  refresh: useWorkspaceRefresh,
} = useWorkspace();
const input = ref(""),
  inputElement = ref(null),
  messagesElement = ref(null);
const preferencesOpen = ref(false), previewOpen = ref(false);
const profilesOpen = ref(false), showUserProfile = ref(false);
const profiles = conversationStyles;
const activeProfile = computed(() => chatStyle(currentChat.value)?.id || "");
async function applyProfile(profile) {
  if (state.sending || state.sessionsLoading) return;
  if (!currentChat.value) newChat();
  setChatPreferences(`## 当前场景：${profile.title}\n${profile.instruction}`, profile.id);
  profilesOpen.value = false;
}
const preferences = reactive({ name: "", language: "", style: "", tools: "", interests: "", notes: "" });
const preferenceFields = [
  { key: "name", label: "如何称呼你", placeholder: "例如：小林" },
  { key: "language", label: "交流语言", options: ["中文", "English", "中英双语"] },
  { key: "style", label: "回答风格", options: ["简洁直接", "详细解释", "先结论后解释", "分步骤说明"] },
  { key: "tools", label: "常用工具", placeholder: "例如：Python、VS Code" },
  { key: "interests", label: "兴趣与关注", placeholder: "例如：阅读、跑步、人工智能" },
  { key: "notes", label: "其他偏好", placeholder: "还有什么希望助手了解的？" },
];
const preferenceMarkdown = computed(() => {
  const rows = preferenceFields.filter(field => preferences[field.key].trim()).map(field => `## ${field.label}\n${preferences[field.key].trim()}`);
  return rows.length ? `# 我的个人偏好\n\n${rows.join("\n\n")}\n\n请根据这些偏好与我交流，并记住适合长期保留的信息。` : "";
});
const userProfile = ref(null), profileLoading = ref(false), profileError = ref("");
const savingPreferences = ref(false);
let profileRequest = 0;
function preferenceStorageKey(user) { return `cm.assistant.preferences.${encodeURIComponent(user)}`; }
function fillPreferences() {
  for (const key of Object.keys(preferences)) preferences[key] = userProfile.value?.preferences?.[key] || "";
}
async function loadProfile({ onboarding = false } = {}) {
  const user = state.user, request = ++profileRequest;
  profileLoading.value = true;
  profileError.value = "";
  try {
    const result = await api(`/api/profile?user_id=${encodeURIComponent(user)}`);
    if (user !== state.user || request !== profileRequest) return;
    userProfile.value = result;
    fillPreferences();
    let visited = false;
    try { visited = localStorage.getItem(preferenceStorageKey(user) + ".visited") === "true"; } catch {}
    if (onboarding && !result.items?.length && !visited) {
      // Legacy browser settings are only a draft until explicitly saved.
      let draft;
      try { draft = JSON.parse(localStorage.getItem(preferenceStorageKey(user)) || "null"); } catch {}
      if (draft) for (const key of Object.keys(preferences)) if (typeof draft[key] === "string") preferences[key] = draft[key];
      preferencesOpen.value = true;
    }
  } catch (error) {
    if (user === state.user && request === profileRequest) profileError.value = error.message;
  } finally {
    if (user === state.user && request === profileRequest) profileLoading.value = false;
  }
}
watch(() => state.user, () => {
  userProfile.value = null;
  preferencesOpen.value = previewOpen.value = false;
  for (const key of Object.keys(preferences)) preferences[key] = "";
  loadProfile({ onboarding: true });
}, { immediate: true, flush: "sync" });
watch(() => state.sending, (sending, wasSending) => { if (wasSending && !sending) loadProfile(); });
function skipPreferences() {
  try { localStorage.setItem(preferenceStorageKey(state.user) + ".visited", "true"); } catch {}
  preferencesOpen.value = false;
}
async function openPreferences() {
  const user = state.user;
  await loadProfile();
  if (user === state.user && !profileError.value) preferencesOpen.value = true;
}
async function submitPreferences() {
  if (savingPreferences.value || state.sending || state.sessionsLoading || profileLoading.value) return;
  const user = state.user;
  savingPreferences.value = true;
  profileError.value = "";
  try {
    const changes = Object.fromEntries(Object.entries(preferences).filter(([key, value]) => value !== (userProfile.value?.preferences?.[key] || "")));
    const result = await api("/api/profile", { method: "PUT", body: JSON.stringify({user_id: user, preferences: changes}) });
    if (user !== state.user) return;
    userProfile.value = result;
    try { localStorage.removeItem(preferenceStorageKey(user)); } catch {}
    skipPreferences();
    fillPreferences();
    await useWorkspaceRefresh();
    notify("个人偏好已保存，后续会话自动使用。");
  } catch (error) { if (user === state.user) profileError.value = error.message; }
  finally { savingPreferences.value = false; }
}
const suggestions = [
  "我现在主要使用什么编程语言？",
  "我以前有哪些编程偏好？",
  "有哪些需要注意的饮食过敏？",
  "我有哪些常用的工作流程？",
];
const recentMemories = computed(() =>
  state.memories
    .filter((memory) => memory.state_role === "current")
    .slice(0, 2),
);
function useMemory(memory) {
  input.value = `关于“${memory.memory_value || memory.content}”，你记得哪些信息？`;
  inputElement.value?.focus();
}
async function scroll() {
  await nextTick();
  if (messagesElement.value)
    if (state.focusMessageId) {
      const target = [...messagesElement.value.querySelectorAll('[data-message-id]')].find(item => item.dataset.messageId === state.focusMessageId);
      target?.scrollIntoView({ block: "center" });
    } else messagesElement.value.scrollTop = messagesElement.value.scrollHeight;
}
watch(
  () => [
    state.currentChatId,
    currentChat.value?.messages.length,
    state.sending,
    state.focusMessageId,
  ],
  scroll,
  { immediate: true },
);
async function createChat() {
  showUserProfile.value = false;
  newChat();
  await nextTick();
  inputElement.value?.focus();
}
async function send(text = input.value) {
  if (!text.trim() || state.sending || state.sessionsLoading) return;
  input.value = "";
  if (!currentChat.value) newChat();
  const pending = sendMessage(text);
  await scroll();
  await pending;
  await scroll();
  inputElement.value?.focus();
}
function keydown(event) {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    send();
  }
}
</script>
<template>
  <div id="lp-assistant" class="page assistant-page">
    <AppDialog v-model:open="profilesOpen" class="profiles-dialog" :title="$t('选择对话偏好')">
      <p class="profiles-intro">{{ $t('选择适合此刻的交流方式，点击即可应用。') }}</p>
      <div class="preference-cards">
        <button v-for="profile in profiles" :key="profile.id" type="button"
          class="preference-card" :class="{ selected: activeProfile === profile.id }"
          :aria-pressed="activeProfile === profile.id"
          :disabled="state.sending || state.sessionsLoading" @click="applyProfile(profile)">
          <span class="preference-icon" :class="`preference-icon--${profile.id}`"><AppIcon :name="profile.icon" /></span>
          <span class="preference-copy">
            <strong>{{ $t(profile.title) }}</strong>
            <span>{{ $t(profile.description) }}</span>
          </span>
          <span class="preference-indicator"><AppIcon :name="activeProfile === profile.id ? 'check' : 'chevron'" /></span>
        </button>
      </div>
      <div class="profiles-footer"><AppIcon name="chat" /><span>{{ $t('应用到当前对话，随时可以切换。') }}</span></div>
    </AppDialog>
    <div v-if="state.sessionsLoading" class="subtle" role="status">{{ $t("正在加载会话…") }}</div>
    <AppDialog v-model:open="preferencesOpen" :title="$t('让助手先了解你')">
        <form class="preferences-form" @submit.prevent="submitPreferences">
          <p class="subtle">{{ $t('保存为长期偏好，跨会话生效；留空可删除对应设置。') }}</p>
          <p v-if="profileError" class="profile-error" role="alert">{{ profileError }}</p>
          <fieldset :disabled="savingPreferences || profileLoading || state.sending" class="preferences-fields">
          <label v-for="field in preferenceFields" :key="field.key">{{ $t(field.label) }}
            <select v-if="field.options" v-model="preferences[field.key]"><option value="">{{ $t("请选择") }}</option><option v-if="preferences[field.key] && !field.options.includes(preferences[field.key])" :value="preferences[field.key]">{{ preferences[field.key] }}</option><option v-for="option in field.options" :key="option">{{ $t(option) }}</option></select>
            <textarea v-else-if="field.key === 'notes'" v-model="preferences[field.key]" :placeholder="$t(field.placeholder)" rows="2" maxlength="2000" />
            <input v-else v-model="preferences[field.key]" :placeholder="$t(field.placeholder)" maxlength="500" />
          </label>
          </fieldset>
          <button type="button" class="text-button" @click="previewOpen = !previewOpen">{{ $t(previewOpen ? '收起' : '预览') }} Markdown</button>
          <pre v-if="previewOpen" class="preferences-preview">{{ preferenceMarkdown || $t('填写偏好后生成') }}</pre>
          <button class="button full" :disabled="savingPreferences || profileLoading || state.sending || state.sessionsLoading">{{ $t("保存并开始对话") }}</button>
        </form>
      <button class="text-button preferences-skip" @click="skipPreferences">{{ $t("稍后填写") }}</button>
    </AppDialog>
    <p v-if="profileError && !preferencesOpen" class="profile-error" role="alert">{{ profileError }}</p>
    <div class="assistant-shell" :class="{ 'profile-mode': showUserProfile }">
      <aside class="conversation-sidebar">
        <button class="button full preferences-trigger" :disabled="state.sending || state.sessionsLoading" @click="profilesOpen = true">{{ $t("切换偏好") }}<AppIcon name="layers"/></button>
        <button class="button full preferences-trigger" @click="openPreferences">{{ $t("偏好设置") }}<span>{{ preferencesOpen ? '−' : '+' }}</span></button>
        <button class="button full preferences-trigger user-profile-trigger" :class="{ active: showUserProfile }" :aria-pressed="showUserProfile" @click="showUserProfile = true">{{ $t("用户画像") }}<AppIcon name="brain" /></button>

        <button
          class="button full"
          :disabled="state.sending || state.sessionsLoading"
          @click="createChat"
        >
          <AppIcon name="plus" />{{ $t("新建会话") }}
        </button>
        <div class="nav-label">{{ $t("最近会话") }}</div>
        <div class="conversation-list">
          <button
            v-for="chat in state.chats"
            :key="chat.id"
            class="conversation-item"
            :class="{ active: chat.id === state.currentChatId }"
            :disabled="state.sending || state.sessionsLoading"
            @click="showUserProfile = false; selectChat(chat.id)"
          >
            <AppIcon name="chat" /><span>{{ chat.title }}</span>
          </button>
        </div>
      </aside>
      <UserProfileView v-if="showUserProfile" @close="showUserProfile = false" />
      <div v-else class="conversation-main">
        <div class="chat-topline">
          <span>{{ $t(currentChat?.title || "新会话") }}</span>
          <div class="mobile-chat-tools">
            <select
              :value="state.currentChatId"
              :disabled="state.sending || state.sessionsLoading"
              :aria-label="$t('选择会话')"
              @change="selectChat($event.target.value)"
            >
              <option v-if="!state.chats.length">{{ $t("新会话") }}</option>
              <option
                v-for="chat in state.chats"
                :key="chat.id"
                :value="chat.id"
              >
                {{ chat.title }}
              </option></select
            ><button
              class="icon-button"
              :disabled="state.sending || state.sessionsLoading"
              :aria-label="$t('新建会话')"
              @click="createChat"
            >
              <AppIcon name="plus" />
            </button>
          </div>
          <button
            class="icon-button"
            :disabled="state.sending || !currentChat"
            :aria-label="$t('删除当前会话')"
            @click="deleteChat"
          >
            <AppIcon name="trash" />
          </button>
        </div>
        <div ref="messagesElement" class="messages" aria-live="polite">
          <div v-if="!currentChat?.messages.length" class="chat-empty">
            <div class="chat-empty-mark"><AppIcon name="chat" /></div>
            <h2>{{ $t("今天，从哪件事聊起？") }}</h2>
            <div class="suggestions">
              <button
                v-for="question in suggestions"
                :key="question"
                class="suggestion"
                @click="send(question)"
              >
                {{ $t(question) }}<span>↗</span>
              </button>
            </div>
            <div v-if="recentMemories.length" class="chat-recent">
              <div class="chat-recent-heading">
                <span>{{ $t("最近记住的事") }}</span
                ><RouterLink to="/memories">{{ $t("管理记忆 ↗") }}</RouterLink>
              </div>
              <button
                v-for="memory in recentMemories"
                :key="memory.id"
                class="chat-memory-row"
                @click="useMemory(memory)"
              >
                <span
                  class="memory-type-dot"
                  :style="{ background: types[memory.memory_type]?.color }"
                /><span>{{ memory.content }}</span
                ><AppIcon name="chevron" />
              </button>
            </div>
          </div>
          <article
            v-for="(message, index) in currentChat?.messages || []"
            :key="index"
            class="message"
            :data-message-id="message.id"
            :data-source-focus="message.id && message.id === state.focusMessageId ? 'true' : null"
            :class="
              message.role === 'user'
                ? 'user'
                : message.error
                  ? 'error'
                  : 'assistant'
            "
          >
            <div class="message-avatar">
              <template v-if="message.role === 'user'">{{ $t("你") }}</template
              ><AppIcon v-else name="memory" />
            </div>
            <div class="message-body">
              <b>{{ $t(message.role === "user" ? "你" : "个人助手") }}</b>
              <p>{{ message.text }}</p>
              <small v-if="message.pending" class="subtle"
                >{{ $t("正在思考并检索记忆…") }}</small
              >
              <details v-if="message.refs?.length" class="evidence-list">
                <summary>{{ $t("参考了 {count} 条记忆", { count: message.refs.length }) }}</summary>
                <div
                  v-for="reference in message.refs"
                  :key="reference.id"
                  class="evidence-card"
                >
                  <p>{{ reference.content }}</p>
                  <small
                    >{{
                      $t(types[reference.memory_type]?.label ||
                      reference.memory_type)
                    }}
                    ·
                    {{
                      $t(roles[reference.state_role]?.label || reference.state_role)
                    }}
                    <template v-if="reference.version"> · {{ $t("版本") }} {{reference.version}} · {{ $t("来源") }} {{reference.source_refs?.length || 0}}</template>
                    <template v-else> · {{ $t("匹配分数") }} {{ Number(reference.score || 0).toFixed(3) }}</template></small
                  >
                  <RouterLink class="text-button" :to="{ name: 'memories', query: { record: reference.id } }">{{ $t("查看记忆与来源 ↗") }}</RouterLink>
                </div>
              </details>
              <small v-for="warning in message.warnings || []" :key="warning" class="subtle">{{ warning }}</small>
              <small v-if="message.memory_results?.length" class="subtle">{{ $t("自动记忆结果：") }}{{ message.memory_results.map(formatMemoryDecision).join('；') }}</small>
              <small v-if="memoryStatusNames[message.memory_status]" class="subtle memory-processing-status">{{ $t(memoryStatusNames[message.memory_status]) }}</small>
              <div v-if="message.role === 'user'" class="message-actions">
                <button class="text-button" @click="openMemory(message.text)">
                  {{ $t("保存为记忆") }}
                </button>
              </div>
            </div>
          </article>
        </div>
        <div class="composer-wrap">
          <form class="composer" @submit.prevent="send()">
            <textarea
              ref="inputElement"
              v-model="input"
              rows="2"
              :aria-label="$t('发送消息')"
              :placeholder="$t('问问与自己有关的事…')"
              maxlength="10000"
              required
              @keydown="keydown"
            />
            <div class="composer-bottom">
              <label class="auto-memory-toggle"><input
                v-model="state.autoRemember"
                type="checkbox"
                :disabled="state.sending"
              />{{ $t("自动记忆") }}</label
              ><button
                class="send-button"
                :disabled="state.sending || state.sessionsLoading || !input.trim()"
                :aria-label="$t('发送')"
              >
                <AppIcon name="arrowUp" />
              </button>
            </div>
          </form>
        </div>
      </div>
      <WorkingMemoryPanel v-if="!showUserProfile" :memory="currentChat?.working_state || null" :sending="state.sending" />
    </div>
  </div>
</template>
<style scoped>
.user-profile-trigger.active { border-color:var(--blue); background:var(--accent-soft); color:var(--blue); }
.assistant-shell.profile-mode { grid-template-columns:190px minmax(0,1fr); }
.profile-mode>.user-profile-page { grid-column:2 / -1; min-height:0; height:100%; }
@media(max-width:1250px) { .assistant-shell.profile-mode { grid-template-columns:minmax(0,1fr); } .profile-mode>.user-profile-page { grid-column:1 / -1; } }
@media(max-width:1050px) { .profile-mode>.user-profile-page { height:auto; } }
.profile-error { color:#d87e7e; font-size:12px; }
.preferences-fields { border:0; padding:0; margin:0; display:grid; gap:13px; min-width:0; }

.profiles-dialog { width:min(520px, calc(100vw - 32px)); padding:28px; border-radius:20px; }
.profiles-dialog :deep(.dialog-heading) { margin-bottom:8px; gap:16px; }
.profiles-dialog :deep(.dialog-heading h2) { font-size:20px; letter-spacing:-.4px; }
.profiles-intro { margin:0 0 24px; color:var(--muted); font-size:13px; line-height:1.7; }
.preference-cards { display:grid; gap:10px; }
.preference-card { display:flex; align-items:center; gap:16px; width:100%; padding:18px; border:1px solid var(--line); border-radius:14px; background:var(--surface, var(--paper)); color:var(--ink); text-align:left; cursor:pointer; font:inherit; transition:background .15s, border-color .15s; }
.preference-card:hover { background:var(--surface-hover, #f0f3fa); border-color:var(--muted); }
.preference-card.selected { background:var(--accent-soft, #edf1fc); border-color:var(--blue); }
.preference-card:focus-visible { outline:2px solid var(--blue); outline-offset:3px; }
.preference-card:disabled { opacity:.5; cursor:wait; }
.preference-icon { display:flex; align-items:center; justify-content:center; flex:0 0 44px; height:44px; border-radius:12px; background:var(--accent-soft, #edf1fc); color:var(--violet); }
.preference-icon--work { background:var(--success-soft, #edf5f0); color:var(--green); }
.preference-icon--study { background:var(--warning-soft, #faf3e7); color:var(--amber); }
.preference-icon :deep(svg) { width:22px; height:22px; }
.preference-copy { display:grid; gap:5px; min-width:0; flex:1; }
.preference-copy strong { font-size:14px; font-weight:600; }
.preference-copy > span { color:var(--muted); font-size:12px; line-height:1.7; }
.preference-indicator { flex:0 0 18px; color:var(--muted); }
.selected .preference-indicator { color:var(--blue); }
.preference-indicator :deep(svg) { width:18px; height:18px; }
.profiles-footer { display:flex; align-items:center; gap:8px; margin-top:22px; padding-top:16px; border-top:1px solid var(--line); color:var(--muted); font-size:12px; }
.profiles-footer :deep(svg) { width:15px; height:15px; }
@media(max-width:540px) { .profiles-dialog { padding:22px 18px; } .preference-card { padding:15px 12px; gap:12px; } .preference-icon { flex-basis:38px; height:38px; } }
.preferences-skip{margin:0 24px 20px}.preferences-trigger{display:flex;justify-content:space-between;margin-bottom:12px}.preferences-form{padding:20px 24px;display:grid;gap:13px;margin:0 0 20px;padding-bottom:18px;border-bottom:1px solid var(--line)}.preferences-form label{display:grid;gap:6px;font-size:11px;color:var(--muted)}.preferences-form input,.preferences-form select,.preferences-form textarea{width:100%;min-width:0;padding:8px;border:1px solid var(--line);border-radius:6px;background:var(--surface);color:var(--text);font:inherit}.preferences-preview{white-space:pre-wrap;overflow-wrap:anywhere;max-height:180px;overflow:auto;font-size:10px;line-height:1.7}.conversation-sidebar:has(.preferences-form){overflow:auto}.conversation-sidebar:has(.preferences-form) .conversation-list{flex:none;max-height:250px}
.assistant-shell{display:grid;grid-template-columns:190px minmax(0,1fr) 265px;grid-template-rows:minmax(0,1fr)}
.conversation-sidebar{width:auto;min-height:0;overflow:hidden}
.conversation-list{flex:1;min-height:0;overscroll-behavior:contain}
.conversation-sidebar>.button,.conversation-sidebar>.nav-label,.conversation-note{flex-shrink:0}
.conversation-main{min-height:0;overflow:hidden}
.messages{min-height:0;overscroll-behavior:contain}
.chat-topline,.composer-wrap{flex-shrink:0}
@media(max-width:1250px){.assistant-shell{grid-template-columns: minmax(0,1fr) 250px}.conversation-sidebar{display:none}}
@media(max-width:1050px){.assistant-page{height:auto;min-height:calc(100dvh - 70px)}.assistant-shell{display:flex;flex:none;flex-direction:column;overflow:visible}.conversation-main{flex:none;height:calc(100dvh - 110px);min-height:320px}}
.evidence-card .text-button { margin-top:8px; }
.message[data-source-focus="true"] { outline:1px solid var(--blue); outline-offset:8px; border-radius:5px; }
</style>
