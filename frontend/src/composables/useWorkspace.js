import { reactive, computed, inject } from "vue";
import { api, post } from "../lib/api";
import { decisionNames } from "../lib/format";

export const WorkspaceKey = Symbol("workspace");
export function useWorkspace() {
  return inject(WorkspaceKey);
}
function read(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
}
export function createWorkspace() {
  const storedUser = read("cm.user", "demo-user");
  const state = reactive({
    user:
      typeof storedUser === "string" && storedUser.trim()
        ? storedUser
        : "demo-user",
    overview: null,
    memories: [],
    loading: false,
    error: "",
    connected: false,
    updatedAt: "",
    toast: "",
    chats: [],
    currentChatId: null,
    sending: false,
    autoRemember: true,
    sessionsLoading: false,
    memoryDraft: null,
    inspectedRecord: null,
    focusMessageId: "",
    confirm: null,
  });
  let loadVersion = 0,
    toastTimer,
    confirmResolve;
  let sessionsVersion = 0;
  let inspectVersion = 0, sourceVersion = 0;
  const currentChat = computed(() =>
    state.chats.find((c) => c.id === state.currentChatId),
  );
  function notify(text) {
    state.toast = text;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      state.toast = "";
    }, 4200);
  }
  function persist(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      notify("浏览器存储空间不足，本次会话仅在当前页面保留。");
    }
  }
  function saveChats() {
    persist(`cm.chats.${state.user}`, state.chats);
  }
  function loadChats() {
    const chats = read(`cm.chats.${state.user}`, []);
    state.chats = Array.isArray(chats)
      ? chats
          .filter(
            (c) => c && typeof c.id === "string" && Array.isArray(c.messages),
          )
          .map((c) => ({
            ...c,
            title: String(c.title || "新会话"),
            messages: c.messages
              .filter((m) => m && ["user", "assistant"].includes(m.role))
              .map((m) => ({
                ...m,
                text: String(m.text || ""),
                pending: false,
                refs: Array.isArray(m.refs)
                  ? m.refs.filter((r) => r && typeof r.content === "string")
                  : [],
              })),
          }))
      : [];
    state.currentChatId = state.chats[0]?.id || null;
  }
  async function refresh() {
    const version = ++loadVersion,
      user = state.user;
    state.loading = true;
    state.error = "";
    try {
      const [summary, list] = await Promise.all([
        api(`/api/overview?user_id=${encodeURIComponent(user)}`),
        api(
          `/api/memories?user_id=${encodeURIComponent(user)}&include_archived=true&limit=1000&view=all`,
        ),
      ]);
      if (version !== loadVersion) return;
      state.overview = summary;
      state.memories = list.items;
      state.connected = true;
      state.updatedAt = new Date().toLocaleTimeString("zh-CN", {
        hour12: false,
      });
    } catch (error) {
      if (version !== loadVersion) return;
      state.error = `暂时无法同步：${error.message} 请刷新重试。`;
      state.connected = false;
    } finally {
      if (version === loadVersion) state.loading = false;
    }
  }
  async function refreshChats() {
    const version = ++sessionsVersion, user = state.user;
    state.sessionsLoading = true;
    try {
      const result = await api(`/api/sessions?user_id=${encodeURIComponent(user)}`);
      if (version !== sessionsVersion || user !== state.user || state.sending) return;
      const remote = result.items;
      const remoteIds = new Set(remote.map((chat) => chat.id));
      const local = state.chats.filter((chat) => !chat.persisted && !remoteIds.has(chat.id));
      state.chats = [...remote, ...local];
      if (!state.chats.some((chat) => chat.id === state.currentChatId))
        state.currentChatId = state.chats[0]?.id || null;
      saveChats();
    } catch (error) {
      if (version === sessionsVersion) notify(`会话恢复失败：${error.message}`);
    } finally {
      if (version === sessionsVersion) state.sessionsLoading = false;
    }
  }
  async function initialize() {
    await Promise.all([refresh(), refreshChats()]);
  }
  function switchUser(value) {
    const user = value.trim().toLowerCase();
    if (!user || state.sending) return;
    ++sessionsVersion;
    ++loadVersion;
    ++inspectVersion;
    ++sourceVersion;
    state.user = user;
    persist("cm.user", user);
    state.overview = null;
    state.memories = [];
    state.connected = false;
    state.memoryDraft = null;
    state.inspectedRecord = null;
    state.focusMessageId = "";
    state.updatedAt = "";
    resolveConfirm(false);
    loadChats();
    initialize();
  }
  function askConfirm(title, text, action = "确认删除") {
    resolveConfirm(false);
    state.confirm = { title, text, action };
    return new Promise((resolve) => {
      confirmResolve = resolve;
    });
  }
  function resolveConfirm(value) {
    state.confirm = null;
    if (confirmResolve) {
      confirmResolve(value);
      confirmResolve = null;
    }
  }
  function openMemory(content = "") {
    state.memoryDraft = {
      content,
      memory_type: "semantic",
      tags: "",
      memory_key: "",
      memory_value: "",
      consent: false,
    };
  }
  async function saveMemory(draft) {
    const payload = { ...draft, user_id: state.user };
    if (draft.consent)
      payload.tags = [draft.tags, "sensitive"].filter(Boolean).join(",");
    const result = await post("/api/memories", payload);
    if (result.decision === "DROP") throw new Error(decisionNames.DROP);
    state.memoryDraft = null;
    notify(decisionNames[result.decision] || "记忆已保存");
    await refresh();
  }
  async function deleteMemory(id) {
    const user = state.user;
    if (
      !(await askConfirm(
        "删除这条记忆？",
        "删除后，记忆正文会从本地数据库移除。此操作无法撤销。",
      ))
    )
      return;
    try {
      await api(
        `/api/memories/${encodeURIComponent(id)}?user_id=${encodeURIComponent(user)}`,
        { method: "DELETE" },
      );
      notify("记忆已删除");
      await refresh();
    } catch (error) {
      notify(error.message);
    }
  }
  async function runRetention() {
    const user = state.user;
    if (
      !(await askConfirm(
        "检查记忆保留度？",
        "系统将归档低价值的非保护记忆，已归档内容仍可查看。",
        "执行检查",
      ))
    )
      return;
    try {
      const result = await post("/api/maintenance/retention", {
        user_id: user,
      });
      notify(`检查完成，归档 ${result.archived_ids.length} 条记忆`);
      await refresh();
    } catch (error) {
      notify(error.message);
    }
  }
  function newChat() {
    if (state.sending || state.sessionsLoading) return;
    ++sourceVersion;
    state.focusMessageId = "";
    const empty = state.chats.find((c) => !c.messages.length);
    if (empty) state.currentChatId = empty.id;
    else {
      const chat = { id: crypto.randomUUID(), title: "新会话", messages: [] };
      state.chats.unshift(chat);
      state.currentChatId = chat.id;
      saveChats();
    }
  }
  function selectChat(id) {
    if (!state.sending) { ++sourceVersion; state.currentChatId = id; state.focusMessageId = ""; }
  }
  async function openSourceThread(id, messageId = "") {
    const user = state.user;
    if (state.sending || !id) return;
    const version = ++sourceVersion;
    try {
      const chat = await api(`/api/sessions/${encodeURIComponent(id)}?user_id=${encodeURIComponent(user)}`);
      if (user !== state.user || version !== sourceVersion) return;
      state.chats = [chat, ...state.chats.filter(item => item.id !== id)];
      state.currentChatId = id;
      state.focusMessageId = messageId;
      saveChats();
    } catch (error) { if (user === state.user && version === sourceVersion) notify(`来源会话不可用：${error.message}`); }
  }
  async function inspectMemory(id) {
    const user = state.user;
    const version = ++inspectVersion;
    try {
      const record = await api(`/api/memories/${encodeURIComponent(id)}?user_id=${encodeURIComponent(user)}`);
      if (user === state.user && version === inspectVersion) state.inspectedRecord = record;
    } catch (error) { if (user === state.user && version === inspectVersion) notify(error.message); }
  }
  async function deleteChat() {
    const id = state.currentChatId, user = state.user;
    if (!id || state.sending || state.sessionsLoading) return;
    if (
      !(await askConfirm(
        "删除这个会话？",
        "删除服务端会话和当前浏览器缓存，已保存的长期记忆仍会保留。",
      ))
    )
      return;
    if (user !== state.user) return;
    const chat = state.chats.find((c) => c.id === id);
    if (chat?.persisted) {
      try {
        await api(`/api/sessions/${encodeURIComponent(id)}?user_id=${encodeURIComponent(user)}`, { method: "DELETE" });
      } catch (error) {
        notify(error.message);
        return;
      }
    }
    if (user !== state.user) return;
    state.chats = state.chats.filter((c) => c.id !== id);
    state.currentChatId = state.chats[0]?.id || null;
    saveChats();
  }
  async function sendMessage(text) {
    text = text.trim();
    if (!text || state.sending || state.sessionsLoading) return false;
    state.focusMessageId = "";
    if (currentChat.value && !currentChat.value.persisted && currentChat.value.messages.length) {
      const next = { id: crypto.randomUUID(), title: "新会话", messages: [] };
      state.chats.unshift(next);
      state.currentChatId = next.id;
      notify("旧版记录已保留，已为连续对话创建新会话。");
    }
    if (!currentChat.value) newChat();
    const chat = currentChat.value,
      user = state.user;
    chat.messages.push({ role: "user", text });
    if (chat.title === "新会话") chat.title = text.slice(0, 20);
    chat.messages.push({
      role: "assistant",
      text: "",
      pending: true,
      refs: [],
    });
    const reply = chat.messages[chat.messages.length - 1];
    state.sending = true;
    try {
      if (!chat.persisted) {
        await post("/api/sessions", { user_id: user, thread_id: chat.id });
        chat.persisted = true;
      }
      const result = await post("/api/chat", {
        user_id: user,
        thread_id: chat.id,
        message: text,
        auto_remember: state.autoRemember,
      }, { timeoutMs: 300000 });
      chat.persisted = true;
      reply.text = result.answer;
      reply.refs = result.references || [];
      reply.memory_results = result.memory_results || [];
      reply.memory_status = result.memory_status || "";
      reply.warnings = result.warnings || [];
      if (reply.warnings.length) notify(reply.warnings.join(" "));
    } catch (error) {
      reply.text = `这次查询没有完成：${error.message} 你的消息已保留，可以重新发送。`;
      reply.error = true;
    } finally {
      reply.pending = false;
      state.sending = false;
      saveChats();
      await refresh();
    }
    return true;
  }
  function dispose() {
    ++sourceVersion;
    ++inspectVersion;
    ++loadVersion;
    ++sessionsVersion;
    clearTimeout(toastTimer);
    resolveConfirm(false);
  }
  loadChats();
  return {
    state,
    currentChat,
    initialize,
    refreshChats,
    refresh,
    switchUser,
    notify,
    askConfirm,
    resolveConfirm,
    openMemory,
    saveMemory,
    deleteMemory,
    runRetention,
    newChat,
    selectChat,
    openSourceThread,
    inspectMemory,
    deleteChat,
    sendMessage,
    dispose,
  };
}
