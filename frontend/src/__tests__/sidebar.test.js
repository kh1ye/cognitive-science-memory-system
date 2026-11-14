import { afterEach, beforeEach, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createRouter, createMemoryHistory } from 'vue-router';
import App from '../App.vue';
import { t } from '../lib/i18n';

let wrapper;
beforeEach(()=>{
  localStorage.clear();
  vi.stubGlobal('fetch',vi.fn(async path=>({ok:true,json:async()=>path.startsWith('/api/overview')?{total_count:0}: {items:[]}})));
});
afterEach(()=>{wrapper?.unmount();wrapper=null;vi.unstubAllGlobals();});
async function render(){
  const routes=['evaluations','connections','overview','install','assistant','memories','memory-gallery','forgetting', 'evolution'].map(name=>({path:`/${name}`,name,component:{template:'<div />'},meta:{title:name==='overview'?'系统总览':name}}));
  const router=createRouter({history:createMemoryHistory(),routes});
  await router.push('/overview');
  await router.isReady();
  wrapper=mount(App,{global:{plugins:[router],stubs:{MemoryForm:true,AppDialog:true}}});
  await flushPromises();
  return router;
}
it('toggles the navigation rail, keeps accessible labels, preserves routes and persists preference',async()=>{
  const router=await render();
  expect(wrapper.find('.layout').classes()).not.toContain('sidebar-collapsed');
  await wrapper.find('[aria-label="收起侧边栏"]').trigger('click');
  expect(wrapper.find('.layout').classes()).toContain('sidebar-collapsed');
  expect(wrapper.find('[aria-label="展开侧边栏"]').attributes('aria-expanded')).toBe('false');
  expect(localStorage.getItem('cm.sidebarCollapsed')).toBe('true');
  const memories=wrapper.find('nav [aria-label="记忆管理"]');
  expect(memories.attributes('data-tooltip')).toBe('记忆管理');
  expect(wrapper.find('.profile').attributes('data-tooltip')).toContain('切换用户空间');
  await memories.trigger('click');
  await flushPromises();
  expect(router.currentRoute.value.name).toBe('memories');
  expect(wrapper.find('.layout').classes()).toContain('sidebar-collapsed');
  wrapper.unmount();wrapper=null;
  await render();
  expect(wrapper.find('.layout').classes()).toContain('sidebar-collapsed');
  await wrapper.find('[aria-label="展开侧边栏"]').trigger('click');
  expect(wrapper.find('nav [aria-label="记忆管理"]').attributes('data-tooltip')).toBeUndefined();
  expect(localStorage.getItem('cm.sidebarCollapsed')).toBe('false');
});
it('updates the title and accessible labels on language change and keeps the preference',async()=>{
  const router=await render();
  await wrapper.find('.language-picker select').setValue('en');
  expect(document.title).toBe('Overview · Cognitive Science Memory System');
  expect(document.documentElement.lang).toBe('en');
  expect(localStorage.getItem('cm.language')).toBe('en');
  expect(wrapper.find('[aria-label="Collapse sidebar"]').exists()).toBe(true);
  expect(wrapper.find('[aria-label="Main navigation"]').exists()).toBe(true);
  expect(t('检查完成，归档 3 条记忆')).toBe('Retention check complete. 3 memories archived.');
  expect(t('设置未保存：网络错误')).toBe('Settings were not saved: 网络错误');
  wrapper.unmount();wrapper=null;
  await render();
  expect(wrapper.find('.language-picker select').element.value).toBe('en');
  expect(document.documentElement.lang).toBe('en');
});
it('refreshes the shared catalog on memory navigation and returning to the tab',async()=>{
  const router=await render();
  const reads=()=>fetch.mock.calls.filter(([path])=>path.startsWith('/api/memories?')).length;
  const initial=reads();
  await router.push('/memory-gallery');await flushPromises();
  expect(reads()).toBe(initial+1);
  await router.push('/memories');await flushPromises();
  expect(reads()).toBe(initial+2);
  window.dispatchEvent(new Event('focus'));await flushPromises();
  expect(reads()).toBe(initial+3);
  await router.push('/assistant');await flushPromises();
  window.dispatchEvent(new Event('focus'));await flushPromises();
  expect(reads()).toBe(initial+3);
});
