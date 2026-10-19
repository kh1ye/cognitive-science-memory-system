import { describe, expect, it } from "vitest";
import { afterState, decisionSummary, evidenceParts, metricExplanation } from "../lib/evolution";

function trace(decision) {
  return {
    result: { decision, memory: { content: "我喜欢喝茶。", state_role: decision === "CANDIDATE" ? "candidate" : "current" } },
    previous: { content: "我喜欢喝咖啡。", state_role: "current" },
    steps: [{ fields: [] }],
    config: { write_threshold: 0.42, cpe_commit_threshold: 0.7, minimum_evidence_count: 2, evidence_consistency_threshold: 0.6 },
  };
}
describe("记忆演化解释", () => {
  it("shows retained current and new candidate rather than implying replacement", () => {
    const candidate = trace("CANDIDATE");
    expect(afterState(candidate).map((item) => item.role)).toEqual(["当前", "候选"]);
    expect(decisionSummary(candidate)).toContain("原有当前记忆暂时保留");
    expect(candidate.previous.state_role).toBe("current");
  });
  it("shows old history only after an actual consolidation", () => {
    expect(afterState(trace("CONSOLIDATED")).map((item) => item.role)).toEqual(["历史", "当前"]);
    expect(afterState(trace("REINFORCED"))).toHaveLength(1);
  });
  it("highlights evidence while preserving all original text and overlapping spans", () => {
    const content = "说明：我喜欢喝茶。也喜欢Python。";
    const parts = evidenceParts(content, [{ content: "我喜欢喝茶。" }, { content: "喜欢喝茶" }, { content: "不存在的片段" }]);
    expect(parts.map((part) => part.text).join("")).toBe(content);
    expect(parts.filter((part) => part.highlighted).map((part) => part.text).join("")).toBe("我喜欢喝茶。");
    expect(parts[0].highlighted).toBe(false);
    expect(parts.some((part) => part.label.includes("候选 2"))).toBe(true);
  });
  it("does not mark unrelated text as evidence", () => {
    expect(evidenceParts("hello <script>", [{ content: "不存在" }])).toEqual([
      { text: "hello <script>", highlighted: false, label: "" },
    ]);
  });
  it("explains real thresholds without equating high error with automatic replacement", () => {
    const candidate = trace("CANDIDATE");
    expect(metricExplanation({ label: "预测误差", value: 0.775 }, candidate)).toContain("仍需同时满足证据数量和一致性要求");
    expect(metricExplanation({ label: "一致证据数量", value: 1 }, candidate)).toContain("数量尚不足");
    expect(metricExplanation({ label: "写入分数", value: 0.2 }, candidate)).toContain("低于写入门槛 0.42");
    expect(metricExplanation({ label: "证据一致性", value: 1 }, candidate)).toContain("不能代替数量要求");
  });
  it("keeps privacy and working-layer summaries accurate", () => {
    const blocked = { result: { decision: "DROP", reason: "consent_required", memory: null }, previous: null };
    expect(afterState(blocked)).toEqual([]);
    expect(decisionSummary(blocked)).toContain("未保存正文");
    expect(decisionSummary(trace("KEEP_SESSION_ONLY"))).toContain("仍会持久保存");
  });
});
