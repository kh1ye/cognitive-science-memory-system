import { it, expect, vi } from 'vitest';
import { reactive } from 'vue';
import { mount } from '@vue/test-utils';
import ConnectionsView from '../views/ConnectionsView.vue';
import { WorkspaceKey } from '../composables/useWorkspace';
import { setLanguage } from '../lib/i18n';
it('groups real sources and persisted sessions and combines search and filters',async()=>{
 const state=reactive({user:'alice',memories:[{id:'one',content:'Python',source:'openclaw_plugin',updated_at:'2026-10-30T01:00:00Z'}],chats:[{id:'thread',persisted:true,title:'学习',messages:[],updated_at:'2026-10-30T02:00:00Z'},{id:'local',persisted:false,messages:[]}]});
 const wrapper=mount(ConnectionsView,{global:{provide:{[WorkspaceKey]:{state,refresh:vi.fn(),refreshChats:vi.fn()}},stubs:{RouterLink:{template:'<a><slot/></a>'}}}});
 expect(wrapper.findAll('tbody tr')).toHaveLength(2);
 await wrapper.find('[aria-label="搜索接入实体"]').setValue('openclaw');
 expect(wrapper.findAll('tbody tr')).toHaveLength(1);
 await wrapper.find('.connections-entity').trigger('click');
 expect(wrapper.find('.connections-detail').text()).toContain('Python');
 await wrapper.find('[aria-label="搜索接入实体"]').setValue('');
 await wrapper.find('[aria-label="实体类型"]').findAll('button')[3].trigger('click');
 expect(wrapper.find('tbody').text()).toContain('thread');
 expect(wrapper.find('tbody').text()).not.toContain('local');
 await wrapper.find('[aria-label="实体类型"]').findAll('button')[1].trigger('click');
 expect(wrapper.find('tbody').text()).toContain('暂无 Agent');
 state.memories[0].metadata={agent_id:'agent-python'};
 await wrapper.vm.$nextTick();
 expect(wrapper.find('tbody').text()).toContain('agent-python');
 state.memories=[];state.chats=[];
 await wrapper.vm.$nextTick();
 expect(wrapper.find('.connections-detail').exists()).toBe(false);
 wrapper.unmount();
});

it('translates entity totals while preserving user session titles',async()=>{
 setLanguage('en');
 const state=reactive({user:'alice',memories:[],chats:[
  {id:'one',persisted:true,title:'未命名会话',messages:[],updated_at:'2026-10-30T01:00:00Z'},
  {id:'two',persisted:true,title:'',messages:[],updated_at:'2026-10-30T02:00:00Z'},
 ]});
 const wrapper=mount(ConnectionsView,{global:{provide:{[WorkspaceKey]:{state,refresh:vi.fn(),refreshChats:vi.fn()}},stubs:{RouterLink:{template:'<a><slot/></a>'}}}});
 expect(wrapper.find('.connections-scope').text()).toContain('2 entities');
 expect(wrapper.find('.connections-scope').text()).toContain('2 server-side conversations loaded');
 const titles=wrapper.findAll('.connections-entity strong').map(node=>node.text());
 expect(titles).toContain('未命名会话');
 expect(titles).toContain('Untitled conversation');
 wrapper.unmount();
});
