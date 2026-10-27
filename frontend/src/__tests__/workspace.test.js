import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createWorkspace, WorkspaceKey } from "../composables/useWorkspace";
import AssistantView from "../views/AssistantView.vue";
import MemoriesView from "../views/MemoriesView.vue";

const records = [
  {
    id: "memory-one",
    content: "我喜欢 Python <img src=x onerror=alert(1)>",
    memory_type: "semantic",
    state_role: "current",
    tags: ["preference"],
    evidence_count: 1,
    updated_at: "2026-10-18T00:00:00Z",
    created_at: "2026-10-18T00:00:00Z",
    importance: 0.7,
    write_score: 0.8,
    support_ids: [],
  },
];
const summary = {
  total_count: 1,
  by_type: { semantic: 1 },
  by_role: { current: 1 },
};
const response = (data) => ({ ok: true, json: async () => data });
const resources = [];
function workspace() {
  const value = createWorkspace();
  resources.push(() => value.dispose());
  return value;
}
function mountView(component, value) {
  const wrapper = mount(component, {
    global: { provide: { [WorkspaceKey]: value } },
  });
  resources.push(() => wrapper.unmount());
  return wrapper;
}
function mockApi(search = () => response({ answer: "你好", references: [] })) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path) => {
      if (path === "/api/chat") return search();
      if (path.startsWith("/api/sessions")) return response({ items: [], persisted: true });
      return response(
        path.startsWith("/api/overview") ? summary : { items: records },
      );
    }),
  );
}
beforeEach(() => {
  localStorage.clear();
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value() {
      this.open = true;
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value() {
      this.open = false;
    },
  });
});
afterEach(() => {
  resources
    .splice(0)
    .reverse()
    .forEach((dispose) => dispose());
  vi.unstubAllGlobals();
});

describe("Vue workspace migration", () => {
  it("loads the shared catalog and renders typed objects without legacy scores or delete actions", async () => {
    const typed = { ...records[0], id: "native-tea", content: "我喜欢喝乌龙茶",
      storage_kind: "typed", native_status: "current", can_delete: false,
      importance: null, write_score: null, created_at: null, updated_at: null };
    vi.stubGlobal("fetch", vi.fn(async path => response(
      path.startsWith("/api/overview") ? { ...summary, total_count: 2 } : { items: [typed, ...records] },
    )));
    const value = workspace();
    await value.refresh();
    expect(fetch.mock.calls.some(([url]) => url.includes("/api/memories?") && url.includes("view=all"))).toBe(true);
    const wrapper = mountView(MemoriesView, value);
    expect(wrapper.text()).toContain("乌龙茶");
    expect(wrapper.text()).toContain("Python");
    expect(wrapper.findAll('table button[aria-label="删除记忆"]')).toHaveLength(1);
    expect(wrapper.find(".preview-score").exists()).toBe(false);
    expect(wrapper.get(".memory-preview").text()).toContain("未记录");
    expect(wrapper.text()).not.toContain("NaN");
    await wrapper.get(".memory-preview .button.full").trigger("click");
    expect(wrapper.text()).toContain("不适用");
    expect(wrapper.find(".dialog-actions .danger").exists()).toBe(false);
  });

  it("reads the previous frontend conversation format without losing history", () => {
    localStorage.setItem("cm.user", JSON.stringify("alice"));
    localStorage.setItem(
      "cm.chats.alice",
      JSON.stringify([
        {
          id: "old-chat",
          title: "过去的对话",
          messages: [{ role: "user", text: "Python" }],
        },
      ]),
    );
    const value = workspace();
    expect(value.state.user).toBe("alice");
    expect(value.currentChat.value.messages[0].text).toBe("Python");
  });

  it("ignores stale responses after switching users", async () => {
    const pending = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise((resolve) => pending.push(resolve))),
    );
    const value = workspace();
    const old = value.refresh();
    value.switchUser("bob");
    pending[2](response({ ...summary, total_count: 2 }));
    pending[3](response({ items: [{ ...records[0], content: "bob 的记忆" }] }));
    pending[4](response({ items: [] }));
    await flushPromises();
    pending[0](response(summary));
    pending[1](response({ items: records }));
    await old;
    expect(value.state.user).toBe("bob");
    expect(value.state.overview.total_count).toBe(2);
    expect(value.state.memories[0].content).toBe("bob 的记忆");
  });

  it("updates chat messages and evidence reactively and persists the reply", async () => {
    let completeSearch;
    mockApi(
      () =>
        new Promise((resolve) => {
          completeSearch = resolve;
        }),
    );
    const value = workspace();
    const wrapper = mountView(AssistantView, value);
    await wrapper.get("textarea").setValue("我喜欢什么？");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(value.state.sending).toBe(true);
    expect(wrapper.get('input[type="checkbox"]').element.disabled).toBe(true);
    expect(wrapper.text()).toContain("正在思考并检索记忆");
    completeSearch(
      response({
        answer: records[0].content,
        references: [{ ...records[0], score: 0.9 }],
        memory_results: [{ decision: "WRITE_CURRENT" }],
      }),
    );
    await flushPromises();
    expect(value.state.sending).toBe(false);
    expect(wrapper.text()).toContain(records[0].content);
    expect(wrapper.findAll("details")).toHaveLength(1);
    expect(wrapper.findAll("img")).toHaveLength(0);
    const saved = JSON.parse(localStorage.getItem("cm.chats.demo-user"));
    expect(saved[0].messages[1].text).toContain("Python");
    expect(wrapper.find("h1").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("记忆检索模式");
    await wrapper.get('input[type="checkbox"]').setValue(false);
    expect(value.state.autoRemember).toBe(false);
  });

  it("keeps a failed message and unlocks the composer for retry", async () => {
    mockApi(() => {
      throw new Error("连接失败");
    });
    const value = workspace();
    await value.sendMessage("保留这句话");
    expect(value.state.sending).toBe(false);
    expect(value.currentChat.value.messages[0].text).toBe("保留这句话");
    expect(value.currentChat.value.messages[1].error).toBe(true);
    expect(value.currentChat.value.messages[1].text).toContain("连接失败");
  });

  it("filters memory records using Vue bindings and escapes stored HTML", async () => {
    const value = workspace();
    value.state.memories = records;
    value.state.overview = summary;
    const wrapper = mountView(MemoriesView, value);
    expect(wrapper.text()).toContain("Python");
    expect(wrapper.findAll("img")).toHaveLength(0);
    await wrapper.get('input[aria-label="搜索记忆"]').setValue("不存在");
    expect(wrapper.text()).toContain("没有符合条件的记忆");
    await wrapper.get("input").setValue("Python");
    expect(wrapper.findAll(".memory-content")).toHaveLength(1);
    await wrapper.get("select").setValue("history");
    expect(wrapper.findAll(".memory-content")).toHaveLength(0);
  });

  it("keeps the desktop preview in sync with selection and filtering", async () => {
    const media = vi
      .spyOn(window, "matchMedia")
      .mockReturnValue({ matches: true });
    const value = workspace();
    value.state.memories = [
      records[0],
      {
        ...records[0],
        id: "memory-two",
        content: "过去喜欢 JavaScript",
        state_role: "history",
      },
    ];
    value.state.overview = summary;
    const wrapper = mountView(MemoriesView, value);
    expect(wrapper.get(".memory-preview").text()).toContain("Python");
    await wrapper.findAll(".memory-content")[1].trigger("click");
    expect(wrapper.get(".memory-preview").text()).toContain(
      "过去喜欢 JavaScript",
    );
    expect(wrapper.get("dialog").element.open).toBe(false);
    await wrapper.get('input[aria-label="搜索记忆"]').setValue("Python");
    expect(wrapper.get(".memory-preview").text()).toContain("Python");
    expect(wrapper.get(".memory-preview").text()).not.toContain("JavaScript");
    media.mockRestore();
  });

  it("recovers SQLite sessions into an empty browser and sends only the new turn with the thread id", async () => {
    const remote = { id: "server-thread", title: "服务端会话", persisted: true, messages: [
      { role: "user", text: "我叫小明" }, { role: "assistant", text: "你好小明" },
    ] };
    vi.stubGlobal("fetch", vi.fn(async (path) => {
      if (path.startsWith("/api/sessions")) return response({ items: [remote] });
      if (path === "/api/chat") return response({ answer: "你叫小明", references: [] });
      return response(path.startsWith("/api/overview") ? summary : { items: records });
    }));
    const value = workspace();
    await value.initialize();
    expect(value.state.currentChatId).toBe("server-thread");
    expect(value.currentChat.value.messages).toHaveLength(2);
    value.state.autoRemember = false;
    await value.sendMessage("我叫什么？");
    const call = fetch.mock.calls.find(([path]) => path === "/api/chat");
    expect(JSON.parse(call[1].body)).toEqual({
      user_id: "demo-user", thread_id: "server-thread", message: "我叫什么？", auto_remember: false,
    });
    expect(value.currentChat.value.messages[3].text).toBe("你叫小明");
  });

  it("ignores session recovery from the previous user", async () => {
    let completeOld;
    vi.stubGlobal("fetch", vi.fn(async (path) => {
      if (path === "/api/sessions?user_id=demo-user")
        return new Promise((resolve) => { completeOld = resolve; });
      if (path.startsWith("/api/sessions")) return response({ items: [] });
      return response(path.startsWith("/api/overview") ? summary : { items: [] });
    }));
    const value = workspace();
    const old = value.refreshChats();
    value.switchUser("bob");
    await flushPromises();
    completeOld(response({ items: [{ id: "private-alice", messages: [] }] }));
    await old;
    expect(value.state.user).toBe("bob");
    expect(value.state.chats).toEqual([]);
  });

  it("deletes the server session without deleting long-term memories", async () => {
    mockApi();
    const value = workspace();
    value.state.chats = [{ id: "server-thread", persisted: true, title: "对话", messages: [] }];
    value.state.currentChatId = "server-thread";
    value.state.memories = records;
    const pending = value.deleteChat();
    value.resolveConfirm(true);
    await pending;
    expect(fetch).toHaveBeenCalledWith(
      "/api/sessions/server-thread?user_id=demo-user", expect.objectContaining({ method: "DELETE" }),
    );
    expect(value.state.chats).toEqual([]);
    expect(value.state.memories).toEqual(records);
  });

  it("explains when a successful conversation has no new long-term memory", async () => {
    mockApi(() => response({ answer: "你好", references: [], memory_status: "no_new_memory" }));
    const value = workspace();
    const wrapper = mountView(AssistantView, value);
    await value.sendMessage("你好");
    await flushPromises();
    expect(wrapper.text()).toContain("本轮未发现需要长期保存的新信息");
    expect(value.currentChat.value.messages[1].memory_status).toBe("no_new_memory");
  });

  it("rejects privacy drops without closing the unsaved memory draft", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => response({ decision: "DROP" })),
    );
    const value = workspace();
    value.openMemory("不要记住这句话");
    await expect(value.saveMemory(value.state.memoryDraft)).rejects.toThrow(
      "未保存",
    );
    expect(value.state.memoryDraft.content).toBe("不要记住这句话");
  });
});
