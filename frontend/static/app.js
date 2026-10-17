"use strict";
const $ = (id) => document.getElementById(id);
const icons = {
  overview:
    '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  chat: '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z"/>',
  memory:
    '<rect x="4" y="3" width="16" height="18" rx="3"/><path d="M8 3v18m4-12h4m-4 4h4"/>',
  activity: '<path d="M3 12h4l3-7 4 14 3-7h4"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
  database:
    '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
  book: '<path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1v15"/>',
  external: '<path d="M14 3h7v7m0-7L10 14m-1-9H4v15h15v-5"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  refresh: '<path d="M20 7a8 8 0 1 0 0 10M20 3v5h-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3m-10 0 1 15h12l1-15M10 10v7m4-7v7"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  arrowUp: '<path d="M12 20V4m-6 6 6-6 6 6"/>',
};
const icon = (name) =>
  `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.memory}</svg>`;
function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((el) => {
    el.innerHTML = icon(el.dataset.icon);
  });
}
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (ch) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        ch
      ],
  );
const types = {
  semantic: {
    label: "语义记忆",
    description: "事实、偏好与个人画像",
    color: "#6384c8",
  },
  episodic: { label: "情景记忆", description: "经历与事件", color: "#81a692" },
  procedural: {
    label: "程序记忆",
    description: "方法、流程与习惯",
    color: "#b5a3c9",
  },
  working: {
    label: "工作记忆",
    description: "短时任务与临时信息",
    color: "#cfb781",
  },
};
const roles = {
  current: { label: "当前", color: "#6689c9" },
  candidate: { label: "候选", color: "#d1b174" },
  history: { label: "历史", color: "#9aaacc" },
  working: { label: "工作层", color: "#b6a6ca" },
  archived: { label: "已归档", color: "#d6dce5" },
};
const eventNames = {
  WRITE_CURRENT: "写入长期记忆",
  KEEP_SESSION_ONLY: "保留工作记忆",
  REINFORCE: "强化已有记忆",
  CANDIDATE: "发现候选证据",
  CONSOLIDATE: "完成证据巩固",
  RETRIEVE: "检索记忆",
  RETENTION: "检查保留度",
  USER_DELETE: "删除记忆",
  DROP_PRIVACY: "隐私门拦截",
};
const decisionNames = {
  WRITE_CURRENT: "已保存为当前记忆",
  KEEP_SESSION_ONLY: "已保留在工作层",
  REINFORCED: "已强化已有记忆",
  CANDIDATE: "已进入候选区，等待更多一致证据",
  CONSOLIDATED: "证据已巩固，当前状态已更新",
  DROP: "未保存：请检查隐私标签与保存同意",
};
const formatDate = (value) =>
  new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
function age(value) {
  const seconds = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000);
  return seconds < 60
    ? "刚刚"
    : seconds < 3600
      ? `${Math.floor(seconds / 60)} 分钟前`
      : seconds < 86400
        ? `${Math.floor(seconds / 3600)} 小时前`
        : formatDate(value);
}
function bytes(value) {
  return value < 1024
    ? `${value} B`
    : value < 1048576
      ? `${(value / 1024).toFixed(1)} KB`
      : `${(value / 1048576).toFixed(2)} MB`;
}
function readLocal(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
}
let user = readLocal("cm.user", "demo-user");
if (typeof user !== "string" || !user.trim()) user = "demo-user";
let overview = null,
  memories = [],
  selectedType = "",
  page = 1,
  loadVersion = 0,
  currentChatId = null,
  chats = [],
  busy = false;
let toastTimer;
function toast(text) {
  $("toast").textContent = text;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("toast").hidden = true), 4200);
}
function persist(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    toast("浏览器存储空间不足，本次会话仅在当前页面保留。");
    return false;
  }
}
function saveChats() {
  persist(`cm.chats.${user}`, chats);
}
function loadChats() {
  chats = readLocal(`cm.chats.${user}`, []);
  if (!Array.isArray(chats)) chats = [];
  chats = chats.filter(
    (c) => c && typeof c.id === "string" && Array.isArray(c.messages),
  );
  currentChatId = chats[0]?.id || null;
  renderConversations();
  renderMessages();
}
async function api(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(path, {
      ...options,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error("服务返回异常，请检查服务状态。");
    }
    if (!response.ok)
      throw new Error(data.message || data.detail || "请求失败，请稍后重试。");
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("请求超时，请稍后重试。");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
function post(path, body) {
  return api(path, { method: "POST", body: JSON.stringify(body) });
}
function switchPage() {
  const selected = location.hash.slice(1);
  const name = ["overview", "assistant", "memories"].includes(selected)
    ? selected
    : "overview";
  for (const p of ["overview", "assistant", "memories"])
    $(p + "Page").hidden = p !== name;
  document.querySelectorAll("nav [data-page]").forEach((a) => {
    const active = a.dataset.page === name;
    a.classList.toggle("active", active);
    if (active) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  $("breadcrumbTitle").textContent = {
    overview: "系统总览",
    assistant: "个人助手",
    memories: "记忆管理",
  }[name];
  document.title = `${$("breadcrumbTitle").textContent} · 记忆工作台`;
  if (name === "assistant") renderMessages();
}
function renderOverview() {
  const d = overview;
  $("totalMetric").textContent = d.total_count.toLocaleString();
  $("activeMetric").textContent = d.active_count.toLocaleString();
  $("candidateMetric").textContent = d.by_role.candidate || 0;
  $("storageMetric").textContent = bytes(
    d.storage.mode === "memory"
      ? d.storage.allocated_bytes
      : d.storage.database_bytes + d.storage.wal_bytes,
  );
  $("navCount").textContent = d.total_count;
  $("donutTotal").textContent = d.total_count;
  $("typeChart").innerHTML = Object.entries(types)
    .map(([key, type]) => {
      const count = d.by_type[key] || 0;
      return `<div class="type-row"><div class="type-label"><span style="background:${type.color}"></span>${type.label}</div><div class="bar-track" role="img" aria-label="${type.label} ${count} 条"><div class="bar-fill" style="width:${d.total_count ? (count / d.total_count) * 100 : 0}%;background:${type.color}"></div></div><strong>${count}</strong></div>`;
    })
    .join("");
  let start = 0;
  const slices = [];
  $("stateLegend").innerHTML = Object.entries(roles)
    .map(([key, role]) => {
      const count = d.by_role[key] || 0;
      const end = start + (d.total_count ? (count / d.total_count) * 100 : 0);
      if (count) slices.push(`${role.color} ${start}% ${end}%`);
      start = end;
      return `<div class="legend-row"><span class="legend-dot" style="background:${role.color}"></span>${role.label}<strong>${count}</strong></div>`;
    })
    .join("");
  $("stateDonut").style.background = slices.length
    ? `conic-gradient(${slices.join(",")})`
    : "#edf0f5";
  $("stateDonut").setAttribute(
    "aria-label",
    `共 ${d.total_count} 条记忆，状态详见右侧`,
  );
  $("activityList").innerHTML = d.recent_activity.length
    ? `<div class="activity-head"><span>活动记录</span><span style="text-align:right">时间</span></div>` +
      d.recent_activity
        .map(
          (event) =>
            `<div class="activity-row"><div class="activity-content"><i>${icon(event.event_type === "RETRIEVE" ? "search" : event.event_type === "USER_DELETE" ? "trash" : "layers")}</i><div><b>${esc(eventNames[event.event_type] || event.event_type)}</b><p title="${esc(event.message)}">${esc(event.message)}</p></div></div><time datetime="${esc(event.created_at)}" title="${esc(formatDate(event.created_at))}">${esc(age(event.created_at))}</time></div>`,
        )
        .join("")
    : '<div class="empty">还没有活动。添加第一条记忆，开始积累。</div>';
  $("moduleList").innerHTML = d.modules
    .map(
      (module) =>
        `<div class="module-row"><div><b>${esc(module.name)}</b><small>${esc(module.description)}</small></div><span class="module-status ${module.status === "ready" ? "" : "off"}"><span class="small-dot"></span>${module.status === "ready" ? "已就绪" : "未接入"}</span></div>`,
    )
    .join("");
  $("storageDescription").textContent =
    `SQLite · ${d.storage.mode === "memory" ? "内存模式" : "本地持久化"} · 数据页 ${bytes(d.storage.allocated_bytes)}`;
  $("updatedAt").textContent =
    `更新于 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`;
}
async function refresh() {
  const version = ++loadVersion,
    scope = user;
  $("refreshButton").disabled = true;
  $("loadError").hidden = true;
  try {
    const [summary, list] = await Promise.all([
      api(`/api/overview?user_id=${encodeURIComponent(scope)}`),
      api(
        `/api/memories?user_id=${encodeURIComponent(scope)}&include_archived=true&limit=1000`,
      ),
    ]);
    if (version !== loadVersion) return;
    overview = summary;
    memories = list.items;
    renderOverview();
    renderTabs();
    renderMemories();
    $("connectionDot").style.background = "#84a18d";
    $("connectionLabel").textContent = "本地服务已连接";
  } catch (error) {
    if (version !== loadVersion) return;
    $("loadError").textContent =
      `暂时无法同步：${error.message} 请点击刷新重试。`;
    $("loadError").hidden = false;
    $("connectionDot").style.background = "#c79383";
    $("connectionLabel").textContent = "连接异常";
  } finally {
    if (version === loadVersion) $("refreshButton").disabled = false;
  }
}
function renderTabs() {
  const tabs = [
    ["", "全部记忆"],
    ...Object.entries(types).map(([k, v]) => [k, v.label]),
  ];
  $("memoryTabs").innerHTML = tabs
    .map(
      ([key, label]) =>
        `<button role="tab" aria-selected="${selectedType === key}" class="memory-tab ${selectedType === key ? "active" : ""}" data-type="${key}">${label}<span>${key ? overview?.by_type[key] || 0 : overview?.total_count || 0}</span></button>`,
    )
    .join("");
}
function filtered() {
  const query = $("memorySearch").value.trim().toLowerCase();
  const role = $("stateFilter").value;
  return memories.filter(
    (m) =>
      (!selectedType || m.memory_type === selectedType) &&
      (!role || m.state_role === role) &&
      (!query ||
        [m.content, m.memory_key, m.memory_value, ...m.tags]
          .join(" ")
          .toLowerCase()
          .includes(query)),
  );
}
function renderMemories() {
  const items = filtered();
  const pages = Math.max(1, Math.ceil(items.length / 10));
  page = Math.min(page, pages);
  const rows = items.slice((page - 1) * 10, page * 10);
  $("filteredCount").textContent = `${items.length} 条记录`;
  $("memoryRows").innerHTML = rows.length
    ? rows
        .map(
          (m) =>
            `<tr><td><button class="memory-content" data-detail="${esc(m.id)}">${esc(m.content.length > 90 ? m.content.slice(0, 90) + "…" : m.content)}</button><div class="memory-tags">${esc(m.tags.length ? m.tags.map((t) => "#" + t).join("  ") : m.memory_key || "无标签")}</div></td><td>${esc(types[m.memory_type]?.label || m.memory_type)}</td><td><span class="badge ${roles[m.state_role] ? m.state_role : ""}">${esc(roles[m.state_role]?.label || m.state_role)}</span></td><td>${Number(m.evidence_count)}</td><td>${esc(formatDate(m.updated_at))}</td><td><button class="icon-button" data-delete="${esc(m.id)}" aria-label="删除记忆">${icon("trash")}</button></td></tr>`,
        )
        .join("")
    : '<tr><td colspan="6"><div class="empty">' +
      (memories.length
        ? "没有符合条件的记忆，试试其他筛选条件。"
        : "还没有记忆，点击右上角添加。") +
      "</div></td></tr>";
  $("paginationInfo").textContent =
    `第 ${page} / ${pages} 页 · ${overview?.total_count > memories.length ? `仅加载最近 ${memories.length} 条，共 ${overview.total_count} 条` : "共 " + items.length + " 条"}`;
  $("previousPage").disabled = page <= 1;
  $("nextPage").disabled = page >= pages;
}
function showDetail(id) {
  const m = memories.find((item) => item.id === id);
  if (!m) return;
  const fields = [
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
  $("memoryDetail").innerHTML =
    `<div class="dialog-heading"><h2>记忆详情</h2><button class="icon-button" data-close="detailDialog" aria-label="关闭">×</button></div><p class="detail-content">${esc(m.content)}</p><div class="detail-tags">${m.tags.map((tag) => `<span class="badge">${esc(tag)}</span>`).join("")}</div><dl class="detail-fields">${fields.map(([key, value]) => `<dt>${key}</dt><dd>${esc(value)}</dd>`).join("")}</dl>${m.support_ids.length ? `<p class="form-hint">此记录由 ${m.support_ids.length} 条候选证据巩固而来。</p>` : ""}<div class="dialog-actions"><button class="button danger" data-delete="${esc(m.id)}">删除记忆</button><button class="button" data-close="detailDialog">关闭</button></div>`;
  $("detailDialog").showModal();
}
let confirmResolve = null;
function confirmAction(title, text, action = "确认删除") {
  $("confirmTitle").textContent = title;
  $("confirmText").textContent = text;
  $("acceptConfirm").textContent = action;
  $("confirmDialog").showModal();
  return new Promise((resolve) => (confirmResolve = resolve));
}
function finishConfirm(value) {
  $("confirmDialog").close();
  if (confirmResolve) {
    confirmResolve(value);
    confirmResolve = null;
  }
}
async function deleteMemory(id) {
  const scope = user;
  const record = memories.find((m) => m.id === id);
  if (!record) return;
  if ($("detailDialog").open) $("detailDialog").close();
  if (
    !(await confirmAction(
      "删除这条记忆？",
      "删除后，记忆正文会从本地数据库移除。此操作无法撤销。",
    ))
  )
    return;
  try {
    await api(
      `/api/memories/${encodeURIComponent(id)}?user_id=${encodeURIComponent(scope)}`,
      { method: "DELETE" },
    );
    toast("记忆已删除");
    await refresh();
  } catch (error) {
    toast(error.message);
  }
}
function openMemory(content = "") {
  $("memoryForm").reset();
  $("memoryForm").elements.content.value = content;
  $("formError").textContent = "";
  $("memoryDialog").showModal();
}
function currentChat() {
  return chats.find((c) => c.id === currentChatId);
}
function newChat() {
  if (busy) return;
  const existing = chats.find((c) => !c.messages.length);
  if (existing) currentChatId = existing.id;
  else {
    const chat = { id: crypto.randomUUID(), title: "新会话", messages: [] };
    chats.unshift(chat);
    currentChatId = chat.id;
    saveChats();
  }
  renderConversations();
  renderMessages();
  $("chatInput").focus();
}
function renderConversations() {
  $("conversationList").innerHTML = chats
    .map(
      (chat) =>
        `<button class="conversation-item ${chat.id === currentChatId ? "active" : ""}" data-chat="${esc(chat.id)}" ${busy ? "disabled" : ""}>${icon("chat")}<span>${esc(chat.title)}</span></button>`,
    )
    .join("");
  $("deleteChat").disabled = busy || !currentChat();
  $("mobileNewChat").disabled = busy;
  $("mobileConversation").disabled = busy;
  $("mobileConversation").innerHTML = chats.length
    ? chats
        .map(
          (chat) =>
            `<option value="${esc(chat.id)}" ${chat.id === currentChatId ? "selected" : ""}>${esc(chat.title)}</option>`,
        )
        .join("")
    : "<option>新会话</option>";
}
function renderMessages() {
  const chat = currentChat();
  $("conversationTitle").textContent = chat?.title || "新会话";
  if (!chat?.messages.length) {
    $("messages").innerHTML =
      `<div class="chat-empty"><div class="chat-empty-mark">${icon("chat")}</div><h2>今天，从哪件事聊起？</h2><p>关于你的偏好、过去的经历，或熟悉的工作方式。<br>我会先从已有记忆中寻找线索。</p><div class="suggestions">${["我现在主要使用什么编程语言？", "我以前有哪些编程偏好？", "有哪些需要注意的饮食过敏？"].map((q) => `<button class="suggestion" data-suggest="${esc(q)}">${esc(q)}<span>↗</span></button>`).join("")}</div></div>`;
    return;
  }
  $("messages").innerHTML = chat.messages
    .map(
      (m, index) =>
        `<article class="message ${m.role === "user" ? "user" : m.error ? "error" : "assistant"}"><div class="message-avatar">${m.role === "user" ? "你" : icon("memory")}</div><div class="message-body"><b>${m.role === "user" ? "你" : "个人助手"}</b><p>${esc(m.text)}</p>${m.pending ? '<small class="subtle">正在查找相关记忆…</small>' : ""}${m.refs?.length ? `<details class="evidence-list"><summary>参考了 ${m.refs.length} 条记忆</summary>${m.refs.map((ref) => `<div class="evidence-card"><p>${esc(ref.content)}</p><small>${esc(types[ref.memory_type]?.label || ref.memory_type)} · ${esc(roles[ref.state_role]?.label || ref.state_role)} · 匹配分数 ${Number(ref.score || 0).toFixed(3)}</small></div>`).join("")}</details>` : ""}${m.role === "user" ? `<div class="message-actions"><button class="text-button" data-save-message="${index}">保存为记忆</button></div>` : ""}</div></article>`,
    )
    .join("");
  $("messages").scrollTop = $("messages").scrollHeight;
}
async function sendMessage(text) {
  text = text.trim();
  if (!text || busy) return;
  if (!currentChat()) newChat();
  const chat = currentChat(),
    scope = user;
  const recent = chat.messages
    .filter((m) => m.role === "user")
    .slice(-3)
    .map((m) => m.text)
    .join(" ");
  chat.messages.push({ role: "user", text });
  if (chat.title === "新会话") chat.title = text.slice(0, 20);
  const reply = { role: "assistant", text: "", pending: true };
  chat.messages.push(reply);
  $("chatInput").value = "";
  busy = true;
  $("sendButton").disabled = true;
  $("newChat").disabled = true;
  $("profileButton").disabled = true;
  renderConversations();
  renderMessages();
  try {
    const result = await post("/api/search", {
      user_id: scope,
      query: text,
      recent_focus: recent,
      top_k: 5,
    });
    const preferredRole = result.policy?.history_intent ? "history" : "current";
    const preferred = result.results.filter(
      (m) => m.state_role === preferredRole,
    );
    const pool = preferred.length ? preferred : result.results;
    const references = pool
      .filter((m) => m.retrieval.score >= pool[0].retrieval.score * 0.55)
      .slice(0, 3);
    reply.text = references.length
      ? "从已有记忆中找到以下线索：\n\n" +
        references.map((m) => m.content).join("\n\n")
      : "在当前记忆里还没有找到相关记录。你可以先在记忆管理中添加信息，或换一种更具体的问法。";
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
    busy = false;
    $("sendButton").disabled = false;
    $("newChat").disabled = false;
    $("profileButton").disabled = false;
    saveChats();
    renderConversations();
    renderMessages();
    await refresh();
    $("chatInput").focus();
  }
}
// Navigation and delegated actions use text-safe rendering for all user content.
document.addEventListener("click", (event) => {
  const close = event.target.closest("[data-close]");
  if (close) {
    $(close.dataset.close).close();
    return;
  }
  const go = event.target.closest("[data-go]");
  if (go) location.hash = go.dataset.go;
  const tab = event.target.closest("[data-type]");
  if (tab) {
    selectedType = tab.dataset.type;
    page = 1;
    renderTabs();
    renderMemories();
  }
  const detail = event.target.closest("[data-detail]");
  if (detail) showDetail(detail.dataset.detail);
  const del = event.target.closest("[data-delete]");
  if (del) deleteMemory(del.dataset.delete);
  const conversation = event.target.closest("[data-chat]");
  if (conversation && !busy) {
    currentChatId = conversation.dataset.chat;
    renderConversations();
    renderMessages();
  }
  const suggestion = event.target.closest("[data-suggest]");
  if (suggestion) sendMessage(suggestion.dataset.suggest);
  const save = event.target.closest("[data-save-message]");
  if (save)
    openMemory(currentChat().messages[Number(save.dataset.saveMessage)].text);
});
$("acceptConfirm").onclick = () => finishConfirm(true);
$("cancelConfirm").onclick = () => finishConfirm(false);
$("confirmDialog").addEventListener("cancel", (event) => {
  event.preventDefault();
  finishConfirm(false);
});
$("refreshButton").onclick = refresh;
$("addMemoryButton").onclick = () => openMemory();
$("memorySearch").oninput = () => {
  page = 1;
  renderMemories();
};
$("stateFilter").onchange = () => {
  page = 1;
  renderMemories();
};
$("previousPage").onclick = () => {
  page--;
  renderMemories();
};
$("nextPage").onclick = () => {
  page++;
  renderMemories();
};
$("memoryForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  if (!data.content.trim()) {
    return;
  }
  data.consent = event.target.elements.consent.checked;
  if (data.consent)
    data.tags = [data.tags, "sensitive"].filter(Boolean).join(",");
  data.user_id = user;
  $("saveMemory").disabled = true;
  $("formError").textContent = "";
  try {
    const result = await post("/api/memories", data);
    if (result.decision === "DROP") {
      $("formError").textContent = decisionNames.DROP;
      return;
    }
    $("memoryDialog").close();
    toast(decisionNames[result.decision] || "记忆已保存");
    page = 1;
    await refresh();
  } catch (error) {
    $("formError").textContent = error.message;
  } finally {
    $("saveMemory").disabled = false;
  }
});
$("retentionButton").onclick = async () => {
  if (
    !(await confirmAction(
      "检查记忆保留度？",
      "系统将按保留度规则归档低价值的非保护记忆。已归档内容仍可在管理中心查看。",
      "执行检查",
    ))
  )
    return;
  $("retentionButton").disabled = true;
  try {
    const result = await post("/api/maintenance/retention", { user_id: user });
    toast(`检查完成，归档 ${result.archived_ids.length} 条记忆`);
    await refresh();
  } catch (error) {
    toast(error.message);
  } finally {
    $("retentionButton").disabled = false;
  }
};
$("mobileNewChat").onclick = newChat;
$("mobileConversation").onchange = (event) => {
  if (!busy) {
    currentChatId = event.target.value;
    renderConversations();
    renderMessages();
  }
};
$("newChat").onclick = newChat;
$("chatForm").onsubmit = (event) => {
  event.preventDefault();
  sendMessage($("chatInput").value);
};
$("chatInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    sendMessage(event.target.value);
  }
});
$("deleteChat").onclick = async () => {
  const id = currentChatId;
  if (!id || busy) return;
  if (
    !(await confirmAction(
      "删除这个会话？",
      "仅删除当前浏览器中的会话记录，已保存的个人记忆不会被删除。",
    ))
  )
    return;
  chats = chats.filter((c) => c.id !== id);
  currentChatId = chats[0]?.id || null;
  saveChats();
  renderConversations();
  renderMessages();
};
$("profileButton").onclick = () => {
  $("userInput").value = user;
  $("profileDialog").showModal();
};
$("profileForm").onsubmit = (event) => {
  event.preventDefault();
  const value = $("userInput").value.trim().toLowerCase();
  if (!value) return;
  user = value;
  persist("cm.user", user);
  $("profileName").textContent = user;
  selectedType = "";
  page = 1;
  overview = null;
  memories = [];
  for (const id of [
    "totalMetric",
    "activeMetric",
    "candidateMetric",
    "storageMetric",
    "navCount",
    "donutTotal",
  ])
    $(id).textContent = "—";
  $("typeChart").innerHTML = "";
  $("stateLegend").innerHTML = "";
  $("stateDonut").style.background = "#edf0f5";
  $("activityList").innerHTML = '<div class="empty">正在同步当前空间…</div>';
  $("moduleList").innerHTML = "";
  renderTabs();
  renderMemories();
  loadChats();
  $("profileDialog").close();
  refresh();
};
window.addEventListener("hashchange", switchPage);
$("today").textContent = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "short",
}).format(new Date());
$("profileName").textContent = user;
hydrateIcons();
switchPage();
loadChats();
refresh();
