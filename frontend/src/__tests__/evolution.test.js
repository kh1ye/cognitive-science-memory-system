import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import EvolutionView from "../views/EvolutionView.vue";
import { WorkspaceKey } from "../composables/useWorkspace";

const wrappers = [];
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount());
  vi.unstubAllGlobals();
});
function mountEvolution() {
  const refresh = vi.fn(async () => {});
  const wrapper = mount(EvolutionView, {
    global: { provide: { [WorkspaceKey]: { state: { user: "test-user" }, refresh } } },
  });
  wrappers.push(wrapper);
  return { wrapper, refresh };
}
const trace = {
  result: { decision: "WRITE_CURRENT", memory: {
    id: "record-1", content: "<img src=x onerror=alert(1)>",
    memory_type: "semantic", state_role: "current", tags: [], evidence_count: 1,
    write_score: 0.604, attention_bias: 0.66, source: "evolution_workbench",
  } },
  previous: null,
  events: [{ event_type: "WRITE_CURRENT", message: "通过写入门", details: {} }],
  steps: ["原始输入", "选择性编码", "新旧比较", "巩固决策", "存储结果"].map((title) => ({
    title, description: "真实处理结果", status: "done",
    fields: [{ label: "原文", value: "我喜欢喝茶。" }],
  })),
};
function makeReport(traces = [trace]) {
  return {
    input: { content: "我喜欢喝茶。", user_id: "test-user" },
    extraction: { method: "local_rules", message: "有限本地规则", rejected_count: 0, candidates: [{
      content: "我喜欢喝茶。", memory_key: "drink_preference", memory_value: "茶",
      memory_type: "semantic", tags: ["preference"], importance: 0.7, confidence: 0.8,
    }] },
    traces, outcome: "processed", message: "真实执行",
  };
}
function mockReport(result = makeReport()) {
  const fetch = vi.fn(async () => ({ ok: true, json: async () => result }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
async function submit(wrapper) {
  await wrapper.find("textarea").setValue("我喜欢喝茶。");
  await wrapper.find("form").trigger("submit");
  await flushPromises();
}
describe("一次输入的记忆演化", () => {
  it("only asks for natural language and does not write on mount", () => {
    const fetch = mockReport();
    const { wrapper } = mountEvolution();
    expect(wrapper.findAll("textarea")).toHaveLength(1);
    expect(wrapper.findAll("input, select")).toHaveLength(0);
    expect(fetch).not.toHaveBeenCalled();
  });
  it("automatically reveals all stages and stored JSON after one submission", async () => {
    const fetch = mockReport();
    const { wrapper, refresh } = mountEvolution();
    await submit(wrapper);
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[0][0]).toBe("/api/evolution/analyze");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ user_id: "test-user", content: "我喜欢喝茶。" });
    expect(refresh).toHaveBeenCalledOnce();
    expect(wrapper.findAll(".journey-stage h2").map((heading) => heading.text())).toEqual([
      "用户原话", "自动提取信息", "选择性编码", "新旧比较", "巩固决策", "存储结果",
    ]);
    expect(wrapper.find(".storage-json").isVisible()).toBe(true);
    expect(wrapper.find(".storage-json").text()).toContain("record-1");
    expect(wrapper.findAll("details")).toHaveLength(0);
    expect(wrapper.findAll("img")).toHaveLength(0);
    expect(wrapper.find(".outcome-summary").text()).toContain("已保存为当前长期记忆");
    expect(wrapper.find(".evidence-input mark").text()).toBe("我喜欢喝茶。");
    expect(wrapper.find(".extraction-mapping").text()).toContain("drink_preference");
    expect(wrapper.text()).not.toContain("下一步");
  });
  it("shows a real candidate outcome without fabricating confirmations", async () => {
    const candidate = structuredClone(trace);
    candidate.result.decision = "CANDIDATE";
    candidate.result.memory.state_role = "candidate";
    candidate.previous = { content: "我喜欢咖啡。", state_role: "current", evidence_count: 1 };
    const fetch = mockReport(makeReport([candidate]));
    const { wrapper } = mountEvolution();
    await submit(wrapper);
    expect(wrapper.find(".candidate-notice").text()).toContain("不会为了走完流程而自动补充证据");
    expect(wrapper.find(".comparison").text()).toContain("我喜欢咖啡。");
    expect(wrapper.find(".after-state").text()).toContain("当前");
    expect(wrapper.find(".after-state").text()).toContain("候选");
    expect(wrapper.find(".outcome-summary").text()).toContain("原有当前记忆暂时保留");
    expect(fetch).toHaveBeenCalledOnce();
  });
  it("marks downstream stages as not executed when extraction is empty", async () => {
    const report = makeReport([]);
    report.outcome = "no_new_memory";
    report.extraction.candidates = [];
    mockReport(report);
    const { wrapper } = mountEvolution();
    await submit(wrapper);
    expect(wrapper.findAll(".status-tag.skipped")).toHaveLength(4);
    expect(wrapper.find(".storage-json").exists()).toBe(false);
  });
  it("shows extraction errors without displaying fabricated results", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, json: async () => ({ message: "接口不存在" }) })));
    const { wrapper } = mountEvolution();
    await submit(wrapper);
    expect(wrapper.find('[role="alert"]').text()).toContain("重启后端");
    expect(wrapper.find(".journey").exists()).toBe(false);
  });
  it("prevents duplicate submissions while the request is pending", async () => {
    let finish;
    const fetch = vi.fn(() => new Promise((resolve) => { finish = resolve; }));
    vi.stubGlobal("fetch", fetch);
    const { wrapper } = mountEvolution();
    await wrapper.find("textarea").setValue("我喜欢喝茶。");
    await wrapper.find("form").trigger("submit");
    await wrapper.find("form").trigger("submit");
    expect(fetch).toHaveBeenCalledOnce();
    expect(wrapper.find('[role="status"]').exists()).toBe(true);
    finish({ ok: true, json: async () => makeReport() });
    await flushPromises();
    expect(wrapper.find('[role="status"]').exists()).toBe(false);
  });
});
