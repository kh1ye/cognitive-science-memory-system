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
function mockApi(search = () => response({ results: [], policy: {} })) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path) => {
      if (path === "/api/search") return search();
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
    expect(value.state.sending).toBe(true);
    expect(wrapper.text()).toContain("正在查找相关记忆");
    completeSearch(
      response({
        policy: { history_intent: false },
        results: [{ ...records[0], retrieval: { score: 0.9 } }],
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
