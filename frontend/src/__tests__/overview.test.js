import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick, reactive } from "vue";
import OverviewView from "../views/OverviewView.vue";
import { WorkspaceKey } from "../composables/useWorkspace";
import { moduleState, recentChange } from "../lib/overview";

const wrappers = [];
afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()));

function overview() {
  return {
    total_count: 3, active_count: 3,
    by_role: { current: 1, candidate: 2 }, by_type: { semantic: 3 },
    storage: { mode: "memory", allocated_bytes: 4096, database_bytes: 0, wal_bytes: 0 },
    modules: [
      { name: "选择性编码", description: "价值筛选", status: "ready" },
      { name: "语言模型", description: "模型已配置 · 尚未验证连接", status: "configured" },
      { name: "向量模型", description: "当前使用词法召回", status: "not_implemented" },
    ],
    recent_activity: [{
      id: "event-1", event_type: "CANDIDATE", message: "引擎事件", memory_id: "memory-1",
      created_at: "2026-10-19T00:00:00Z", details: {},
      related_memory: { content: "我喜欢茶 <img src=x onerror=alert(1)>", state_role: "candidate" },
    }],
  };
}
function view(summary = overview(), values = {}) {
  const state = reactive({ overview: summary, loading: false, user: "alice", error: "", updatedAt: "10:00:00", ...values });
  const refresh = vi.fn();
  const wrapper = mount(OverviewView, {
    global: {
      provide: { [WorkspaceKey]: { state, refresh } },
      stubs: { RouterLink: { props: ["to"], template: '<a :href="to"><slot /></a>' } },
    },
  });
  wrappers.push(wrapper);
  return { wrapper, state, refresh };
}

describe("总览局部优化", () => {
  it("summarizes real per-user states while preserving existing metric cards", () => {
    const { wrapper } = view();
    expect(wrapper.find(".snapshot-copy h2").text()).toContain("1 条为当前记忆，2 条候选证据等待巩固");
    expect(wrapper.findAll(".metric > div").map((item) => item.text())).toEqual(["记忆总量", "活跃记忆", "待巩固证据", "本地存储"]);
    expect(wrapper.findAll(".snapshot-actions a").map((link) => link.attributes("href"))).toEqual(["/evolution", "/memories"]);
  });
  it("explains changes and labels linked text as a current snapshot with safe rendering", () => {
    const { wrapper } = view();
    expect(wrapper.find(".change-explanation").text()).toContain("未在此步骤替换旧记忆");
    expect(wrapper.find(".related-record").text()).toContain("当前快照 / 候选");
    expect(wrapper.find("blockquote").text()).toContain("<img src=x onerror=alert(1)>");
    expect(wrapper.findAll("img")).toHaveLength(0);
  });
  it("never displays deleted body even if a deletion event unexpectedly carries it", () => {
    const summary = overview();
    summary.recent_activity[0].event_type = "USER_DELETE";
    const { wrapper } = view(summary);
    expect(wrapper.find(".related-record").exists()).toBe(false);
    expect(wrapper.find(".missing-record").text()).toContain("仅展示操作");
    expect(wrapper.text()).not.toContain("onerror");
  });
  it("distinguishes empty, unavailable and stale snapshots", async () => {
    const empty = overview();
    empty.total_count = 0;
    empty.by_role = {};
    empty.recent_activity = [];
    const { wrapper, state } = view(empty);
    expect(wrapper.find(".overview-empty a").attributes("href")).toBe("/evolution");
    expect(wrapper.find(".snapshot-copy h2").text()).toContain("还是空的");
    const unavailable = view(null, { error: "同步失败" }).wrapper;
    expect(unavailable.find(".snapshot-copy h2").text()).toContain("暂未取得");
    expect(unavailable.find(".overview-empty a").exists()).toBe(false);
    state.error = "同步失败";
    await nextTick();
    expect(wrapper.find(".snapshot-copy p").text()).toContain("上次成功同步的快照");
  });
  it("shows honest module labels and refresh remains available", async () => {
    const { wrapper, refresh } = view();
    expect(wrapper.findAll(".module-status").map((item) => item.text())).toEqual(["已就绪", "已配置", "暂未实现"]);
    expect(wrapper.find(".module-note").text()).toContain("不代表已验证连接");
    await wrapper.find(".heading-actions button").trigger("click");
    expect(refresh).toHaveBeenCalledOnce();
    expect(moduleState({ name: "语言模型", status: "ready" }).label).toBe("已配置");
    expect(moduleState({ name: "未知", status: "unexpected" }).label).toBe("状态未知");
  });
  it("reports recorded event counts rather than invented daily trends", () => {
    expect(recentChange({ event_type: "RETRIEVE", details: { result_ids: ["one", "two"] } })).toContain("2 条");
    expect(recentChange({ event_type: "RETENTION", details: { archived_ids: [] } })).toContain("0 条");
    expect(recentChange({ event_type: "REINFORCE", details: { evidence_count: 3 } })).toContain("此次操作后为 3 条");
  });
});
