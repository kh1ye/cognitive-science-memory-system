<script setup>
import { computed, nextTick, ref, watch } from "vue";
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
    messagesElement.value.scrollTop = messagesElement.value.scrollHeight;
}
watch(
  () => [
    state.currentChatId,
    currentChat.value?.messages.length,
    state.sending,
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
  <div class="page assistant-page">
    <div v-if="state.sessionsLoading" class="subtle" role="status">正在恢复服务端会话…</div>
    <div class="assistant-shell">
      <aside class="conversation-sidebar">
        <button
          class="button full"
          :disabled="state.sending || state.sessionsLoading"
          @click="createChat"
        >
          <AppIcon name="plus" />新建会话
        </button>
        <div class="nav-label">最近会话</div>
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
        <p class="conversation-note">
          会话保存在服务端 SQLite<br />按用户空间分别记录
        </p>
      </aside>
      <div class="conversation-main">
        <div class="chat-topline">
          <span>{{ currentChat?.title || "新会话" }}</span>
          <div class="mobile-chat-tools">
            <select
              :value="state.currentChatId"
              :disabled="state.sending || state.sessionsLoading"
              aria-label="选择会话"
              @change="selectChat($event.target.value)"
            >
              <option v-if="!state.chats.length">新会话</option>
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
              aria-label="新建会话"
              @click="createChat"
            >
              <AppIcon name="plus" />
            </button>
          </div>
          <button
            class="icon-button"
            :disabled="state.sending || !currentChat"
            aria-label="删除当前会话"
            @click="deleteChat"
          >
            <AppIcon name="trash" />
          </button>
        </div>
        <div ref="messagesElement" class="messages" aria-live="polite">
          <div v-if="!currentChat?.messages.length" class="chat-empty">
            <div class="chat-empty-mark"><AppIcon name="chat" /></div>
            <h2>今天，从哪件事聊起？</h2>
            <p>
              关于你的偏好、过去的经历，或熟悉的工作方式。<br />我会先从已有记忆中寻找线索。
            </p>
            <div class="suggestions">
              <button
                v-for="question in suggestions"
                :key="question"
                class="suggestion"
                @click="send(question)"
              >
                {{ question }}<span>↗</span>
              </button>
            </div>
            <div v-if="recentMemories.length" class="chat-recent">
              <div class="chat-recent-heading">
                <span>最近记住的事</span
                ><RouterLink to="/memories">管理记忆 ↗</RouterLink>
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
            :class="
              message.role === 'user'
                ? 'user'
                : message.error
                  ? 'error'
                  : 'assistant'
            "
          >
            <div class="message-avatar">
              <template v-if="message.role === 'user'">你</template
              ><AppIcon v-else name="memory" />
            </div>
            <div class="message-body">
              <b>{{ message.role === "user" ? "你" : "个人助手" }}</b>
              <p>{{ message.text }}</p>
              <small v-if="message.pending" class="subtle"
                >正在思考并检索记忆…</small
              >
              <details v-if="message.refs?.length" class="evidence-list">
                <summary>参考了 {{ message.refs.length }} 条记忆</summary>
                <div
                  v-for="reference in message.refs"
                  :key="reference.id"
                  class="evidence-card"
                >
                  <p>{{ reference.content }}</p>
                  <small
                    >{{
                      types[reference.memory_type]?.label ||
                      reference.memory_type
                    }}
                    ·
                    {{
                      roles[reference.state_role]?.label || reference.state_role
                    }}
                    <template v-if="reference.version"> · 版本 {{reference.version}} · 来源 {{reference.source_refs?.length || 0}}</template>
                    <template v-else> · 匹配分数 {{ Number(reference.score || 0).toFixed(3) }}</template></small
                  >
                </div>
              </details>
              <small v-for="warning in message.warnings || []" :key="warning" class="subtle">{{ warning }}</small>
              <small v-if="message.memory_results?.length" class="subtle">自动记忆结果：{{ message.memory_results.map(formatMemoryDecision).join('；') }}</small>
              <small v-if="memoryStatusNames[message.memory_status]" class="subtle memory-processing-status">{{ memoryStatusNames[message.memory_status] }}</small>
              <div v-if="message.role === 'user'" class="message-actions">
                <button class="text-button" @click="openMemory(message.text)">
                  保存为记忆
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
              aria-label="发送消息"
              placeholder="问问与自己有关的事…"
              maxlength="10000"
              required
              @keydown="keydown"
            />
            <div class="composer-bottom">
              <label class="auto-memory-toggle"><input
                v-model="state.autoRemember"
                type="checkbox"
                :disabled="state.sending"
              />自动记忆</label
              ><button
                class="send-button"
                :disabled="state.sending || state.sessionsLoading || !input.trim()"
                aria-label="发送"
              >
                <AppIcon name="arrowUp" />
              </button>
            </div>
          </form>
          <p class="composer-note">
            会话用于连续对话；自动记忆会提取可长期保留的信息。敏感信息请手动确认保存。
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
