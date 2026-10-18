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
    memoryDraft: null,
    confirm: null,
  });
  let loadVersion = 0,
    toastTimer,
    confirmResolve;
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
          `/api/memories?user_id=${encodeURIComponent(user)}&include_archived=true&limit=1000`,
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
  function switchUser(value) {
    const user = value.trim().toLowerCase();
    if (!user || state.sending) return;
    ++loadVersion;
    state.user = user;
    persist("cm.user", user);
    state.overview = null;
    state.memories = [];
    state.connected = false;
    state.memoryDraft = null;
    state.updatedAt = "";
    resolveConfirm(false);
    loadChats();
    refresh();
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
    if (state.sending) return;
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
    if (!state.sending) state.currentChatId = id;
  }
  async function deleteChat() {
    const id = state.currentChatId;
    if (!id || state.sending) return;
    if (
      !(await askConfirm(
        "删除这个会话？",
        "仅删除当前浏览器中的会话，已保存的个人记忆不会被删除。",
      ))
    )
      return;
    state.chats = state.chats.filter((c) => c.id !== id);
    state.currentChatId = state.chats[0]?.id || null;
    saveChats();
  }
  async function sendMessage(text) {
    text = text.trim();
    if (!text || state.sending) return false;
    if (!currentChat.value) newChat();
    const chat = currentChat.value,
      user = state.user;
    const recent = chat.messages
      .filter((m) => m.role === "user")
      .slice(-3)
      .map((m) => m.text)
      .join(" ");
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
      const result = await post("/api/search", {
        user_id: user,
        query: text,
        recent_focus: recent,
        top_k: 5,
      });
      const role = result.policy?.history_intent ? "history" : "current";
      const preferred = result.results.filter((m) => m.state_role === role);
      const pool = preferred.length ? preferred : result.results;
      const references = pool
        .filter((m) => m.retrieval.score >= pool[0].retrieval.score * 0.55)
        .slice(0, 3);
      reply.text = references.length
        ? "从已有记忆中找到以下线索：\n\n" +
          references.map((m) => m.content).join("\n\n")
        : "在当前记忆里还没有找到相关记录。你可以先添加信息，或换一种更具体的问法。";
      reply.refs = references.map((m) => ({
        id: m.id,
        content: m.content,
        memory_type: m.memory_type,
        state_role: m.state_role,
        score: m.retrieval.score,
      }));
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
    ++loadVersion;
    clearTimeout(toastTimer);
    resolveConfirm(false);
  }
  loadChats();
  return {
    state,
    currentChat,
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
    deleteChat,
    sendMessage,
    dispose,
  };
}
