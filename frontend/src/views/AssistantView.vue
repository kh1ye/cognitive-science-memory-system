<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue";
import AppDialog from "../components/AppDialog.vue";
import WorkingMemoryPanel from "../components/WorkingMemoryPanel.vue";
import AppIcon from "../components/AppIcon.vue";
import { useWorkspace } from "../composables/useWorkspace";
import { types, roles, memoryStatusNames, formatMemoryDecision } from "../lib/format";
const {
  state,
  currentChat,
  newChat,
  selectChat,
  deleteChat,
  sendMessage,
  openMemory,
} = useWorkspace();
const input = ref(""),
  inputElement = ref(null),
  messagesElement = ref(null);
const preferencesOpen = ref(false), previewOpen = ref(false);
const profilesOpen = ref(false), activeProfile = ref("");
const profiles = [
  { id: "daily", title: "日常陪伴", icon: "chat", description: "轻松交流，关注日常生活与兴趣。", instruction: "请采用自然、温和、简洁的交流方式，优先关注我的日常生活与兴趣。" },
  { id: "work", title: "专注工作", icon: "layers", description: "先给结论，再提供清晰可执行的步骤。", instruction: "请先给结论，再给可执行的步骤。表达简洁，明确区分已知信息与需要确认的事项。" },
  { id: "study", title: "学习探索", icon: "book", description: "循序渐进，用例子帮助理解。", instruction: "请循序渐进地解释，结合具体例子，必要时通过提问确认我的理解。" },
];
async function applyProfile(profile) {
  if (state.sending || state.sessionsLoading) return;
  if (!currentChat.value) newChat();
  currentChat.value.preference_context = `# 对话偏好\n${preferenceMarkdown.value}\n\n## 当前场景：${profile.title}\n${profile.instruction}`;
  activeProfile.value = profile.id;
  profilesOpen.value = false;
}
watch(() => state.currentChatId, () => { activeProfile.value = ""; });
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
function preferenceStorageKey(user) { return `cm.assistant.preferences.${encodeURIComponent(user)}`; }
watch(() => state.user, (user) => {
  for (const key of Object.keys(preferences)) preferences[key] = "";
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(preferenceStorageKey(user)) || "null"); } catch {}
  if (saved) for (const key of Object.keys(preferences)) if (typeof saved[key] === "string") preferences[key] = saved[key];
  previewOpen.value = false;
  let visited = false;
  try {
    visited = localStorage.getItem(preferenceStorageKey(user) + ".visited") === "true";
    localStorage.setItem(preferenceStorageKey(user) + ".visited", "true");
  } catch {}
  preferencesOpen.value = !saved && !visited;
}, { immediate: true, flush: "sync" });
async function submitPreferences() {
  if (!preferenceMarkdown.value || state.sending || state.sessionsLoading) return;
  if (!currentChat.value) newChat();
  currentChat.value.preference_context = preferenceMarkdown.value;
  try { localStorage.setItem(preferenceStorageKey(state.user), JSON.stringify({ ...preferences })); } catch {}
  preferencesOpen.value = false;
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
  newChat();
  await nextTick();
  inputElement.value?.focus();
}
async function send(text = input.value) {
  if (!text.trim() || state.sending || state.sessionsLoading) return;
  input.value = "";
  if (!currentChat.value) newChat();
  if (!currentChat.value.preference_context) currentChat.value.preference_context = preferenceMarkdown.value;
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
    <AppDialog v-model:open="profilesOpen" :title="$t('选择对话偏好')">
      <div class="preference-cards"><button v-for="profile in profiles" :key="profile.id" class="preference-card" :class="{ selected: activeProfile === profile.id }" :disabled="state.sending || state.sessionsLoading" @click="applyProfile(profile)"><AppIcon :name="profile.icon"/><strong>{{ $t(profile.title) }}</strong><span>{{ $t(profile.description) }}</span><small>{{ $t(activeProfile === profile.id ? '当前模式' : '应用到当前对话 →') }}</small></button></div>
    </AppDialog>
    <div v-if="state.sessionsLoading" class="subtle" role="status">{{ $t("正在加载会话…") }}</div>
    <AppDialog v-model:open="preferencesOpen" :title="$t('让助手先了解你')">
        <form class="preferences-form" @submit.prevent="submitPreferences">
          <label v-for="field in preferenceFields" :key="field.key">{{ $t(field.label) }}
            <select v-if="field.options" v-model="preferences[field.key]"><option value="">{{ $t("请选择") }}</option><option v-for="option in field.options" :key="option">{{ $t(option) }}</option></select>
            <textarea v-else-if="field.key === 'notes'" v-model="preferences[field.key]" :placeholder="$t(field.placeholder)" rows="2" maxlength="2000" />
            <input v-else v-model="preferences[field.key]" :placeholder="$t(field.placeholder)" maxlength="500" />
          </label>
          <button type="button" class="text-button" @click="previewOpen = !previewOpen">{{ $t(previewOpen ? '收起' : '预览') }} Markdown</button>
          <pre v-if="previewOpen" class="preferences-preview">{{ preferenceMarkdown || $t('填写偏好后生成') }}</pre>
          <button class="button full" :disabled="!preferenceMarkdown || state.sending || state.sessionsLoading">{{ $t("保存并开始对话") }}</button>
        </form>
      <button class="text-button preferences-skip" @click="preferencesOpen = false">{{ $t("稍后填写") }}</button>
    </AppDialog>
    <div class="assistant-shell">
      <aside class="conversation-sidebar">
        <button class="button full preferences-trigger" :disabled="state.sending || state.sessionsLoading" @click="profilesOpen = true">{{ $t("切换偏好") }}<AppIcon name="layers"/></button>
        <button class="button full preferences-trigger" @click="preferencesOpen = !preferencesOpen">{{ $t("偏好设置") }}<span>{{ preferencesOpen ? '−' : '+' }}</span></button>

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
            @click="selectChat(chat.id)"
          >
            <AppIcon name="chat" /><span>{{ chat.title }}</span>
          </button>
        </div>
      </aside>
      <div class="conversation-main">
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
      <WorkingMemoryPanel :memory="currentChat?.working_state || null" :sending="state.sending" />
    </div>
  </div>
</template>
<style scoped>
.preference-cards{display:grid;gap:12px;padding:20px 24px 24px}.preference-card{display:grid;grid-template-columns:25px 1fr;gap:8px 12px;padding:18px;border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--text);text-align:left;cursor:pointer}.preference-card:hover,.preference-card.selected{border-color:var(--blue,#a48bc8)}.preference-card>svg{width:20px;height:20px;grid-row:1/4}.preference-card>strong{font-size:14px}.preference-card>span{font-size:12px;color:var(--muted)}.preference-card>small{font-size:11px;color:var(--blue,#a48bc8);margin-top:5px}
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
