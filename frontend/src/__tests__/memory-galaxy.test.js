import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import MemoryGalaxy from '../views/MemoryGalaxyView.vue';
import MemoriesView from '../views/MemoriesView.vue';
import { createWorkspace, WorkspaceKey } from '../composables/useWorkspace';
let wrapper, management, workspace;
beforeEach(()=>{localStorage.clear();wrapper=management=workspace=undefined;});
afterEach(()=>{wrapper?.unmount();management?.unmount();workspace?.dispose();vi.unstubAllGlobals();});
const record=(id,type,content)=>({id,memory_type:type,content,state_role:'current',storage_kind:'legacy',evidence_count:1,tags:[],support_ids:[],updated_at:'2026-10-28T00:00:00Z'});
const response=data=>({ok:true,json:async()=>data});
const list=items=>response({items});
function setup(){workspace ||= createWorkspace();wrapper=mount(MemoryGalaxy,{global:{provide:{[WorkspaceKey]:workspace}}});return wrapper;}
function catalog(items){vi.stubGlobal('fetch',vi.fn(async path=>path.startsWith('/api/overview')?response({total_count:items.length,by_type:{}}):list(items)));}
it('displays the current shared catalog, filters categories and opens safe text details',async()=>{
 catalog([record('one','semantic','我喜欢茶 <img src=x>'),record('two','episodic','昨天看了电影'),record('task','working','临时任务')]);
 workspace=createWorkspace();await workspace.refresh();setup();await flushPromises();
 expect(fetch.mock.calls.find(([path])=>path.startsWith('/api/memories?'))[0]).toContain('user_id=demo-user');
 expect(wrapper.find('select').exists()).toBe(false);
 expect(wrapper.findAll('[data-node]')).toHaveLength(2);
 await wrapper.get('[aria-label="查看记忆：我喜欢茶 <img src=x>"]').trigger('click');
 expect(wrapper.get('[aria-label="记忆节点详情"]').text()).toContain('我喜欢茶 <img src=x>');
 expect(wrapper.find('img').exists()).toBe(false);
 await wrapper.findAll('.galaxy-filters button').find(b=>b.text().includes('情景记忆')).trigger('click');
 expect(wrapper.findAll('[data-node]')).toHaveLength(1);
 expect(wrapper.get('dialog').element.open).toBe(false);
 await wrapper.get('[aria-label="搜索星图记忆"]').setValue('不存在');
 expect(wrapper.text()).toContain('没有找到这段记忆');
});
it('switches both views to the current user and ignores an older catalog response',async()=>{
 const pending=[];
 vi.stubGlobal('fetch',vi.fn(()=>new Promise(resolve=>pending.push(resolve))));
 workspace=createWorkspace();setup();const old=workspace.refresh();workspace.switchUser('alice');
 pending[2](response({total_count:1,by_type:{}}));pending[3](list([record('alice','semantic','alice 的记忆')]));pending[4](list([]));await flushPromises();
 pending[0](response({total_count:1,by_type:{}}));pending[1](list([record('demo','semantic','旧响应')]));await old;await flushPromises();
 expect(wrapper.text()).not.toContain('旧响应');
 expect(wrapper.findAll('[data-node]')).toHaveLength(1);
 expect(wrapper.find('[aria-label="查看记忆：alice 的记忆"]').exists()).toBe(true);
 expect(wrapper.text()).toContain('当前空间 · alice');
});
it('shows shared refresh errors without displaying another space',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>{throw Error('网络断开');}));workspace=createWorkspace();setup();await workspace.refresh();await flushPromises();
 expect(wrapper.text()).toContain('网络断开');expect(wrapper.findAll('[data-node]')).toHaveLength(0);
});
it('loads original typed fields instead of catalog summary fields',async()=>{
 const native={...record('work','semantic','我喜欢茶'),storage_kind:'typed',module:'semantic_assertions'};
 const original={subject:'demo-user',predicate:'preference',value:'茶',evidence_text:'我喜欢茶',version:0,source_refs:[],metadata:{confirmed:false,count:0}};
 vi.stubGlobal('fetch',vi.fn(async path=>path.includes('/api/architecture/objects/semantic_assertions/work?')?response(original):path.startsWith('/api/overview')?response({total_count:1,by_type:{}}):list([native])));
 workspace=createWorkspace();await workspace.refresh();setup();await flushPromises();await wrapper.get('[data-node]').trigger('click');await flushPromises();
 const detail=wrapper.get('[aria-label="记忆节点详情"]');
 expect(detail.text()).toContain('subject');expect(detail.text()).toContain('metadata');expect(detail.text()).toContain('false');
 expect(detail.findAll('dt').map(el=>el.text())).toEqual(Object.keys(original));
 expect(detail.text()).not.toContain('证据数量');expect(detail.text()).not.toContain('分类测试集 · 演示数据');
});
it('keeps management rows, nodes and selected details synchronized after writes, refreshes and deletes',async()=>{
 let rows=[];
 vi.stubGlobal('fetch',vi.fn(async(path,options={})=>{
   if(path==='/api/memories'&&options.method==='POST'){
     rows=[record('new','semantic',JSON.parse(options.body).content)];return response({decision:'WRITE_CURRENT'});
   }
   if(path.startsWith('/api/overview'))return response({total_count:rows.length,by_type:{semantic:rows.length}});
   if(path.startsWith('/api/memories/new?')){
     if(options.method==='DELETE'){rows=[];return response({deleted:true});}
     return response(rows[0]);
   }
   return list(rows);
 }));
 workspace=createWorkspace();setup();management=mount(MemoriesView,{global:{provide:{[WorkspaceKey]:workspace}}});
 await workspace.saveMemory({content:'我喜欢喝茶',memory_type:'semantic'});await flushPromises();
 expect(management.findAll('.memory-content')).toHaveLength(1);expect(wrapper.findAll('[data-node]')).toHaveLength(1);
 await wrapper.get('[data-node]').trigger('click');await flushPromises();
 rows=[record('new','semantic','我喜欢喝乌龙茶')];await workspace.refresh();await flushPromises();
 expect(management.get('.memory-content').text()).toBe('我喜欢喝乌龙茶');
 expect(wrapper.get('[aria-label="记忆节点详情"]').text()).toContain('我喜欢喝乌龙茶');
 const deletion=workspace.deleteMemory('new');workspace.resolveConfirm(true);await deletion;await flushPromises();
 expect(management.findAll('.memory-content')).toHaveLength(0);expect(wrapper.findAll('[data-node]')).toHaveLength(0);
 expect(wrapper.get('dialog').element.open).toBe(false);
});

it('opens an overlay without expanding the page and restores scroll styles on Escape and unmount',async()=>{
 catalog([record('one','semantic','我喜欢茶')]);
 workspace=createWorkspace();await workspace.refresh();setup();await flushPromises();
 const rootOverflow=document.documentElement.style.overflow, bodyOverflow=document.body.style.overflow;
 const node=wrapper.get('[data-node]');
 expect(wrapper.find('.galaxy-layout dialog').exists()).toBe(false);
 expect(wrapper.find('.galaxy-layout aside').exists()).toBe(false);
 await node.trigger('keydown',{key:'Enter'});await flushPromises();
 expect(wrapper.get('dialog').element.open).toBe(true);
 expect(document.documentElement.style.overflow).toBe('hidden');
 expect(document.body.style.overflow).toBe('hidden');
 await wrapper.get('dialog').trigger('cancel');await flushPromises();
 expect(wrapper.get('dialog').element.open).toBe(false);
 expect(document.documentElement.style.overflow).toBe(rootOverflow);
 expect(document.body.style.overflow).toBe(bodyOverflow);
 await node.trigger('click');await flushPromises();wrapper.unmount();wrapper=undefined;
 expect(document.documentElement.style.overflow).toBe(rootOverflow);
 expect(document.body.style.overflow).toBe(bodyOverflow);
});
