import { expect, it, vi } from "vitest";
import { reactive } from "vue";
import { mount } from "@vue/test-utils";
import MemoryForm from "../components/MemoryForm.vue";
import MemoriesView from "../views/MemoriesView.vue";
import { WorkspaceKey } from "../composables/useWorkspace";

it("offers three content types and keeps working-layer records in their content category", async () => {
  const saveMemory = vi.fn(async () => {});
  const state = reactive({
    user: "alice", overview: { total_count: 1, by_type: { semantic: 1 } },
    memoryDraft: { content: "保存操作流程", memory_type: "semantic", tags: "", memory_key: "", memory_value: "", consent: false },
    memories: [{ id: "temporary", content: "工作层中的事实", memory_type: "semantic", state_role: "working", tags: [], source: "user", evidence_count: 1, importance: 0.1, write_score: 0.1, created_at: "2026-10-27T00:00:00Z", updated_at: "2026-10-27T00:00:00Z" }],
  });
  const global = { provide: { [WorkspaceKey]: { state, saveMemory, openMemory: vi.fn(), deleteMemory: vi.fn(), runRetention: vi.fn() } }, stubs: { AppDialog: { template: "<div><slot /></div>" } } };
  const form = mount(MemoryForm, { global });
  expect(form.findAll("select option").map(option => option.element.value).sort()).toEqual(["episodic", "procedural", "semantic"]);
  await form.find("select").setValue("procedural");
  await form.find("form").trigger("submit");
  expect(saveMemory).toHaveBeenCalledWith(expect.objectContaining({ memory_type: "procedural" }));
  form.unmount();
  const view = mount(MemoriesView, { global });
  expect(view.findAll('[role="tab"]')).toHaveLength(4); // All + three content types.
  expect(view.find('[role="tablist"]').text()).not.toContain("工作记忆");
  await view.findAll('[role="tab"]').find(tab => tab.text().includes("语义记忆")).trigger("click");
  expect(view.find("tbody").text()).toContain("工作层中的事实");
  expect(view.find("tbody").text()).toContain("工作层");
  view.unmount();
});
