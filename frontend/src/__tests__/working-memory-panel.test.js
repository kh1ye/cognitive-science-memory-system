import { mount } from '@vue/test-utils';
import { expect,it } from 'vitest';
import WorkingMemoryPanel from '../components/WorkingMemoryPanel.vue';
it('displays actual task fields and clears them when changing to a new chat',async()=>{
 const w=mount(WorkingMemoryPanel,{props:{memory:{goals:['制定周末计划'],constraints:['本次简短'],open_questions:['预算多少'],task_state:{steps:3}}}});
 expect(w.text()).toContain('制定周末计划');expect(w.text()).toContain('本次简短');expect(w.text()).toContain('预算多少');
 await w.setProps({memory:null});expect(w.text()).not.toContain('制定周末计划');expect(w.text()).toContain('尚未提取到明确目标');w.unmount();
});
