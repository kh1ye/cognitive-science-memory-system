import { afterEach, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import EvaluationsView from '../views/EvaluationsView.vue';

let wrapper;
afterEach(()=>{wrapper?.unmount();wrapper=null;vi.unstubAllGlobals();});
const record={id:'run',dataset:'vatsalabench',kind:'batch',name:'expansion',completed:4,planned:5,model:'deepseek-flash',created_at:'2026-10-30T14:45:00+08:00',status:'partial'};
const details={...record,review:'reviewed',metrics:[{key:'AFA',name:'原子事实准确率',dimension:'准确性',value:.25,unit:'percent',valid_n:4,planned_n:5},{key:'CR-AUC',name:'条件保持曲线面积',dimension:'保持性',value:1,unit:'number',valid_n:1,planned_n:5}],efficiency:{samples:3,planned_samples:5,L95:2.9,ATC:106929,SAF:2.91,conditional:true},samples:[{id:'sample',completed:12,planned:12,status:'completed'}],path:'evaluation/Vatsalabench/results/run',report:'报告',config:{}};
function setup(){
 let started=false;
 vi.stubGlobal('fetch',vi.fn(async(path,options={})=>{
   let data;
   if(path==='/api/evaluations/datasets') data={items:[{id:'vatsalabench',name:'Vatsalabench',count:500,metrics:['AFA','CR-AUC']},{id:'memory-150',name:'记忆分类与过滤',count:150,metrics:['分类准确率']}],model_configured:false};
   else if(path==='/api/evaluations/runs') data={items:[record]};
   else if(path==='/api/evaluations/runs/run') data=details;
   else if(path.includes('/samples/')) data={id:'sample',answers:[{id:'BASE-1',question:'What did I say?',answer:'answer',gold:{expected:'reference'},verdict:{correct:0,reason:'different value'},references:[{id:'evidence',content:'original evidence',module:'semantic'}]}],failed_operations:0};
   else if(path==='/api/evaluations/tasks'&&options.method==='POST') {started=true;data={id:'task'};}
   else if(path==='/api/evaluations/tasks') data={items:started?[{id:'task',dataset:'vatsalabench',status:'running',mode:'check',count:1,created_at:'2026-10-30'}]:[]};
   else if(path==='/api/evaluations/tasks/task') data={id:'task',status:'running',mode:'check',created_at:'2026-10-30',log:'Checking samples',progress:[],path:'evaluation/test',message:'检查中'};
   else data={items:[]};
   return {ok:true,json:async()=>data};
 }));
 wrapper=mount(EvaluationsView);
}
it('shows real coverage and conditional efficiency instead of a single total score',async()=>{
 setup();await flushPromises();
 expect(wrapper.text()).toContain('25%');
 expect(wrapper.text()).toContain('有效 1 / 5');
 expect(wrapper.text()).toContain('仅 3 个完成实例 · 整批效率为 NA');
 expect(wrapper.text()).toContain('人工复核完成');
 expect(wrapper.findAll('.eval-dataset')).toHaveLength(2);
 await wrapper.findAll('.eval-detail-tabs button')[1].trigger('click');await flushPromises();
 expect(wrapper.text()).toContain('What did I say?');
 expect(wrapper.text()).toContain('未通过');
 expect(wrapper.text()).toContain('original evidence');
 await wrapper.findAll('.eval-dataset')[1].trigger('click');await flushPromises();
 expect(wrapper.findAll('.eval-metric')).toHaveLength(0);
});
it('starts a data-check task only after submission and opens its progress',async()=>{
 setup();await flushPromises();
 expect(fetch.mock.calls.some(([,options])=>options?.method==='POST')).toBe(false);
 await wrapper.find('.eval-actions .eval-primary').trigger('click');
 expect(wrapper.find('[role="dialog"]').exists()).toBe(true);
 expect(wrapper.find('input[type="password"]').exists()).toBe(false);
 await wrapper.find('form').trigger('submit');await flushPromises();
 const request=fetch.mock.calls.find(([,options])=>options?.method==='POST');
 expect(JSON.parse(request[1].body)).toMatchObject({dataset:'vatsalabench',mode:'check',api_key:''});
 expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
 expect(wrapper.text()).toContain('Checking samples');
});
