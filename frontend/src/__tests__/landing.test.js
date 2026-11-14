import { afterEach, beforeEach, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createRouter, createMemoryHistory } from 'vue-router';
import LandingView from '../views/LandingView.vue';
import App from '../App.vue';

let wrapper;
beforeEach(()=>{localStorage.clear();});
afterEach(()=>{wrapper?.unmount();wrapper=null;vi.unstubAllGlobals();});
function routerFor(){return createRouter({history:createMemoryHistory(),routes:[
  {path:'/',name:'home',component:LandingView,meta:{landing:true,title:'认知记忆系统'}},
  ...['evaluations','connections','overview','install','assistant','memories','memory-gallery','forgetting', 'evolution'].map(name=>({path:`/${name}`,name,component:{template:'<div>工作台</div>'}})),
]});}
it('switches code examples, copies the displayed code and explores an illustrative lifecycle without API writes',async()=>{
  const router=routerFor();await router.push('/');await router.isReady();
  const fetchMock=vi.fn();vi.stubGlobal('fetch',fetchMock);
  const writeText=vi.fn().mockResolvedValue();Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText}});
  wrapper=mount(LandingView,{global:{plugins:[router]}});
  expect(wrapper.find('h1').text()).toContain('让 AI 记住重要的事');
  const steps=wrapper.find('[aria-label="查看记忆变化阶段"]').findAll('button');
  await steps[1].trigger('click');
  expect(wrapper.find('.lp-state-candidate').text()).toBe('候选');
  expect(wrapper.find('.lp-fact strong').text()).toBe('喜欢喝茶');
  await steps[2].trigger('click');
  expect(wrapper.find('.lp-fact strong').text()).toBe('更喜欢咖啡');
  expect(wrapper.find('.lp-state-history').text()).toBe('历史');
  await wrapper.find('[aria-label="接入代码示例"]').findAll('button')[1].trigger('click');
  expect(wrapper.find('pre').text()).toContain('/api/search');
  await wrapper.find('[aria-label="复制接入示例"]').trigger('click');await flushPromises();
  expect(writeText).toHaveBeenCalledWith(expect.stringContaining('/api/search'));
  expect(wrapper.find('[role="status"]').text()).toBe('已复制');
  expect(fetchMock).not.toHaveBeenCalled();
});
it('renders a standalone home and initializes the existing workspace only on entry',async()=>{
  const fetchMock=vi.fn(async path=>({ok:true,json:async()=>path.startsWith('/api/overview')?{total_count:0}:{items:[]}}));
  vi.stubGlobal('fetch',fetchMock);
  const router=routerFor();await router.push('/');await router.isReady();
  wrapper=mount(App,{global:{plugins:[router],stubs:{MemoryForm:true,AppDialog:true}}});
  await flushPromises();
  expect(wrapper.find('.lp-root').exists()).toBe(true);
  expect(wrapper.find('.sidebar').exists()).toBe(false);
  expect(fetchMock).not.toHaveBeenCalled();
  await wrapper.find('.lp-header-cta').trigger('click');await flushPromises();
  expect(router.currentRoute.value.path).toBe('/overview');
  expect(wrapper.find('.sidebar').exists()).toBe(true);
  expect(fetchMock).toHaveBeenCalled();
  await wrapper.find('[aria-label="产品首页"]').trigger('click');await flushPromises();
  expect(wrapper.find('.lp-root').exists()).toBe(true);
});
it('links a completed homepage classification report to its exact evaluation record',async()=>{
 const dataset='b'.repeat(32);
 const report={id:'homepage-report',dataset,model:'mock',planned:1,total:1,accuracy:1,failed:0,results:[{text:'I like tea',expected:'semantic',actual:'semantic',correct:true}]};
 const fetchMock=vi.fn(async(path,options={})=>{
   let data;
   if(path==='/api/evaluations/uploads'&&options.method==='POST') data={id:dataset,name:'custom.json',count:1};
   else if(path===`/api/evaluations/uploads/${dataset}/run`&&options.method==='POST') data=report;
   else throw new Error(`Unexpected request: ${path}`);
   return {ok:true,json:async()=>data};
 });
 vi.stubGlobal('fetch',fetchMock);
 const router=routerFor();await router.push('/');await router.isReady();
 wrapper=mount(LandingView,{global:{plugins:[router]}});
 const input=wrapper.find('input[aria-label="选择评测数据集"]');
 const file=new File(['[]'],'custom.json',{type:'application/json'});
 Object.defineProperty(file,'text',{value:vi.fn().mockResolvedValue(JSON.stringify([{text:'I like tea',expected:'semantic'}]))});
 Object.defineProperty(input.element,'files',{configurable:true,value:[file]});
 await input.trigger('change');
 await wrapper.find('.le-actions button').trigger('click');await flushPromises();
 await wrapper.find('.le-result button').trigger('click');await flushPromises();
 const link=wrapper.findAll('a').find(a=>a.text()==='在评测中心查看 ↗');
 expect(link).toBeTruthy();
 await link.trigger('click');await flushPromises();
 expect(router.currentRoute.value.name).toBe('evaluations');
 expect(router.currentRoute.value.query).toEqual({dataset,run:report.id});
});
