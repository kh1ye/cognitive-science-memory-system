import { afterEach, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import SourceEvidence from "../components/SourceEvidence.vue";
import { createWorkspace } from "../composables/useWorkspace";
const wrappers = [], workspaces = [];
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); workspaces.splice(0).forEach(w => w.dispose()); vi.unstubAllGlobals(); localStorage.clear(); });
const response = data => ({ ok:true, json:async()=>data });
it("shows actual source messages and honestly labels missing legacy evidence", async () => {
  vi.stubGlobal("fetch", vi.fn(async()=>response({ total_count:1,evidence_count:4,legacy_gap:3,items:[{id:"e1",content:"原始证据",source:"conversation_agent",thread_id:"thread-a",message_id:"message-a",created_at:"2026-10-27T00:00:00Z",legacy:1}] })));
  const wrapper=mount(SourceEvidence,{props:{userId:"alice",memoryId:"m1"}});wrappers.push(wrapper);
  await flushPromises();
  expect(wrapper.text()).toContain("3 条计数未保留逐条原文");
  expect(wrapper.findAll("article")).toHaveLength(1);
  expect(wrapper.find("a").attributes("href")).toBe("#/assistant?thread=thread-a&message=message-a");
});
it("ignores old-user evidence responses", async () => {
  let finish;
  vi.stubGlobal("fetch",vi.fn(async path=>path.includes("alice")?new Promise(resolve=>finish=resolve):response({total_count:0,evidence_count:0,items:[]})));
  const wrapper=mount(SourceEvidence,{props:{userId:"alice",memoryId:"m1"}});wrappers.push(wrapper);
  await wrapper.setProps({userId:"bob",memoryId:"m2"});await flushPromises();
  finish(response({total_count:1,items:[{id:"old",content:"alice private"}]}));await flushPromises();
  expect(wrapper.text()).not.toContain("alice private");
});
it("loads a source session with message identity and resolves reference details", async () => {
  vi.stubGlobal("fetch",vi.fn(async path=>response(path.startsWith("/api/sessions/")?{id:"older-thread",persisted:true,messages:[{id:"source-message",role:"user",text:"原话"}]}:{id:"record",content:"来源记录"})));
  const workspace=createWorkspace();workspaces.push(workspace);
  await workspace.openSourceThread("older-thread","source-message");
  expect(workspace.currentChat.value.messages[0].id).toBe("source-message");
  expect(workspace.state.focusMessageId).toBe("source-message");
  await workspace.inspectMemory("record");expect(workspace.state.inspectedRecord.id).toBe("record");
});
it("discards a slower earlier record lookup", async () => {
  let finish;
  vi.stubGlobal("fetch",vi.fn(async path=>path.includes("old-record")?new Promise(resolve=>finish=resolve):response({id:"new-record"})));
  const workspace=createWorkspace();workspaces.push(workspace);
  const old=workspace.inspectMemory("old-record");await workspace.inspectMemory("new-record");
  finish(response({id:"old-record"}));await old;
  expect(workspace.state.inspectedRecord.id).toBe("new-record");
});
