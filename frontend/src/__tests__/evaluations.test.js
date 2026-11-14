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
it('selects the newest run by default even when a batch run exists',async()=>{
 const newer={id:'new-run',dataset:'vatsalabench',kind:'quality',name:'native-20261031',completed:12,planned:12,model:'deepseek-flash',created_at:'2026-10-31T20:57:14+08:00',status:'completed'};
 vi.stubGlobal('fetch',vi.fn(async(path)=>{
   let data;
   if(path==='/api/evaluations/datasets') data={items:[{id:'vatsalabench',name:'Vatsalabench',count:500,metrics:['AFA']}],model_configured:false};
   else if(path==='/api/evaluations/runs') data={items:[newer,record]};
   else if(path==='/api/evaluations/runs/new-run') data={...newer,metrics:[],samples:[],path:'p',review:'unreviewed'};
   else data={items:[]};
   return {ok:true,json:async()=>data};
 }));
 wrapper=mount(EvaluationsView);await flushPromises();
 expect(fetch.mock.calls.some(([path])=>path==='/api/evaluations/runs/new-run')).toBe(true);
 expect(fetch.mock.calls.some(([path])=>path==='/api/evaluations/runs/run')).toBe(false);
});

const uploadId='a'.repeat(32);
const uploadInfo={id:uploadId,name:'custom.json',count:2,label:'上传数据集 · 概念分类',description:'导入的记忆分类数据集，每次按原顺序评测前 20 条。',version:'上传数据集',source:'upload',metrics:['Accuracy'],modes:['classify']};
const uploadReport={id:'upload-report',dataset:uploadId,model:'mock-classifier',planned:2,total:2,accuracy:.5,failed:0,created_at:'2026-11-14T10:00:00+00:00',results:[{id:'case-1',text:'I like tea',expected:'semantic',actual:'semantic',correct:true},{id:'case-2',text:'I walked yesterday',expected:'episodic',actual:'semantic',correct:false}]};
const uploadRecord={id:uploadReport.id,dataset:uploadId,kind:'classification',name:uploadReport.id,completed:2,planned:2,model:uploadReport.model,created_at:uploadReport.created_at,status:'completed',path:`evaluation/uploads/${uploadId}/results/upload-report`};
const otherUploadRecord={...uploadRecord,id:'other-report',name:'other-report',created_at:'2026-11-14T11:00:00+00:00'};
const uploadDetail={...uploadRecord,review:'model',metrics:[{key:'Accuracy',name:'分类准确率',dimension:'分类',value:.5,unit:'percent',valid_n:2}],samples:[],config:{dataset:uploadId,model:uploadReport.model},report:''};
function setupUpload({imported=true,report=false}={}){
 let hasDataset=imported,hasReport=report;
 const fetchMock=vi.fn(async(path,options={})=>{
   let data;
   if(path==='/api/evaluations/datasets') data={items:[{id:'vatsalabench',name:'Vatsalabench',count:500,metrics:['AFA']},...(hasDataset?[uploadInfo]:[])],model_configured:true,configured_model:'mock-classifier',configured_provider:'openai',configured_base_url:'https://mock.example'};
   else if(path==='/api/evaluations/runs') data={items:hasReport?[otherUploadRecord,uploadRecord]:[]};
   else if(path==='/api/evaluations/runs/upload-report') data=uploadDetail;
   else if(path==='/api/evaluations/runs/other-report') data={...uploadDetail,id:'other-report',metrics:[{...uploadDetail.metrics[0],value:.25}]};
   else if(path==='/api/evaluations/runs/upload-report/predictions'||path==='/api/evaluations/runs/other-report/predictions') data={items:uploadReport.results};
   else if(path==='/api/evaluations/uploads'&&options.method==='POST') {hasDataset=true;data={id:uploadId,name:'custom.json',count:2};}
   else if(path===`/api/evaluations/uploads/${uploadId}/run`&&options.method==='POST') {hasReport=true;data=uploadReport;}
   else if(path==='/api/evaluations/tasks') data={items:[]};
   else throw new Error(`Unexpected request: ${options.method||'GET'} ${path}`);
   return {ok:true,json:async()=>data};
 });
 vi.stubGlobal('fetch',fetchMock);
 wrapper=mount(EvaluationsView);
 return fetchMock;
}
async function selectImportFile(){
 const input=wrapper.find('[role="dialog"] input[type="file"]');
 const file=new File(['[]'],'custom.json',{type:'application/json'});
 Object.defineProperty(file,'text',{value:vi.fn().mockResolvedValue(JSON.stringify([{text:'I like tea',expected:'semantic'},{text:'I walked yesterday',expected:'episodic'}]))});
 Object.defineProperty(input.element,'files',{configurable:true,value:[file]});
 await input.trigger('change');
}
it('imports a dataset without running a model and selects it',async()=>{
 const fetchMock=setupUpload({imported:false});await flushPromises();
 await wrapper.find('.eval-actions .eval-secondary').trigger('click');
 await selectImportFile();
 await wrapper.find('[role="dialog"] form').trigger('submit');await flushPromises();
 const posts=fetchMock.mock.calls.filter(([,options])=>options?.method==='POST');
 expect(posts).toHaveLength(1);
 expect(posts[0][0]).toBe('/api/evaluations/uploads');
 expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
 expect(wrapper.find('.eval-dataset[aria-pressed="true"]').text()).toContain('custom.json');
 expect(wrapper.text()).toContain('上传数据集 · 概念分类');
});
it('runs an uploaded dataset through the lightweight endpoint and opens the returned report',async()=>{
 const fetchMock=setupUpload();await flushPromises();
 await wrapper.find('.eval-dataset[aria-pressed="false"]').trigger('click');await flushPromises();
 await wrapper.find('.eval-actions .eval-primary').trigger('click');
 expect(wrapper.text()).toContain('概念分类评测');
 expect(wrapper.find('input[type="password"]').exists()).toBe(false);
 await wrapper.find('[role="dialog"] form').trigger('submit');await flushPromises();
 const run=fetchMock.mock.calls.find(([path,options])=>path===`/api/evaluations/uploads/${uploadId}/run`&&options?.method==='POST');
 expect(run).toBeTruthy();
 expect(fetchMock.mock.calls.some(([path,options])=>path==='/api/evaluations/tasks'&&options?.method==='POST')).toBe(false);
 expect(fetchMock.mock.calls.some(([path])=>path==='/api/evaluations/runs/upload-report')).toBe(true);
 expect(fetchMock.mock.calls.some(([path])=>path==='/api/evaluations/runs/other-report')).toBe(false);
 expect(wrapper.text()).toContain('50%');
 await wrapper.findAll('.eval-detail-tabs button')[1].trigger('click');
 expect(wrapper.text()).toContain('I like tea');
 expect(wrapper.text()).toContain('case-1');
});
it('opens the dataset and exact report requested by the homepage deep link',async()=>{
 window.history.replaceState({},'',`/#/evaluations?dataset=${uploadId}&run=upload-report`);
 const fetchMock=setupUpload({report:true});await flushPromises();
 expect(wrapper.find('.eval-dataset[aria-pressed="true"]').text()).toContain('custom.json');
 expect(fetchMock.mock.calls.some(([path])=>path==='/api/evaluations/runs/upload-report')).toBe(true);
 expect(wrapper.find('.eval-metric strong').text()).toBe('50%');
 window.history.replaceState({},'','/');
});
