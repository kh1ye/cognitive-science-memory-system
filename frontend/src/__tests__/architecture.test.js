import { it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import ArchitectureMemory from '../components/ArchitectureMemory.vue';
import { formatMemoryDecision } from '../lib/format';
it('loads real module records, clears them on user switch and reports actual writes',async()=>{
  const fetchMock=vi.fn(async url=>({ok:true,json:async()=>({items:url.includes('user_id=alice')?[{user_id:'alice',thread_id:'chat',task_id:'task',revision:3,status:'paused',constraints:['English'],active_knowledge:[]}]:[]})}));
  vi.stubGlobal('fetch',fetchMock);
  const wrapper=mount(ArchitectureMemory,{props:{user:'alice'}});
  expect(fetchMock).not.toHaveBeenCalled();
  await wrapper.find('button').trigger('click');await flushPromises();
  expect(wrapper.text()).toContain('English');expect(wrapper.text()).toContain('revision');
  await wrapper.setProps({user:'bob'});await flushPromises();
  expect(wrapper.text()).not.toContain('English');
  expect(wrapper.text()).toContain('暂无此类记录');
  expect(formatMemoryDecision({target_module:'semantic',status:'failed'})).toContain('写入失败');
  wrapper.unmount();vi.unstubAllGlobals();
});
