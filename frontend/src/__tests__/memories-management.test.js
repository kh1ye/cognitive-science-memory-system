import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { reactive } from 'vue';
import MemoriesView from '../views/MemoriesView.vue';
import { WorkspaceKey } from '../composables/useWorkspace';

it('combines source filters, candidate comparison and read-only inspection without mixing users', async () => {
  const base = { memory_type:'semantic', tags:[], evidence_count:1, importance:0.7, created_at:'2026-10-18T00:00:00Z', updated_at:'2026-10-18T00:00:00Z', support_ids:[], memory_key:'drink' };
  const state = reactive({ user:'alice', memories:[
    {...base,id:'old',content:'喜欢茶',state_role:'current',source:'manual'},
    {...base,id:'new',content:'喜欢咖啡',state_role:'candidate',parent_id:'old',source:'chat'},
    {...base,id:'copy',content:'喜欢茶',state_role:'current',source:'manual'},
  ]});
  const fetchMock = vi.fn(); vi.stubGlobal('fetch',fetchMock);
  const wrapper = mount(MemoriesView,{global:{provide:{[WorkspaceKey]:{state,openMemory:vi.fn(),deleteMemory:vi.fn(),runRetention:vi.fn()}}}});
  await wrapper.findAll('.memory-shortcut')[1].trigger('click');
  expect(wrapper.findAll('tbody tr')).toHaveLength(1);
  expect(wrapper.find('tbody').text()).toContain('喜欢咖啡');
  expect(wrapper.find('.memory-relations').text()).toContain('喜欢茶');
  await wrapper.find('[aria-label="筛选来源"]').setValue('manual');
  expect(wrapper.find('tbody').text()).toContain('没有符合条件');
  await wrapper.findAll('button').find(b=>b.text()==='记忆体检').trigger('click');
  expect(wrapper.text()).toContain('相同正文 · 1 组');
  expect(fetchMock).not.toHaveBeenCalled();
  state.user='bob'; state.memories=[];
  await wrapper.vm.$nextTick();
  expect(wrapper.find('[aria-label="筛选来源"]').element.value).toBe('');
  expect(wrapper.text()).not.toContain('喜欢咖啡');
  wrapper.unmount(); vi.unstubAllGlobals();
});
