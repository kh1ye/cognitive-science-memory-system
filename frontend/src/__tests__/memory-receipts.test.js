import { expect, it } from 'vitest';
import { formatMemoryDecision } from '../lib/format';
it('distinguishes saved facts, pending candidates, conflicts and older incomplete receipts',()=>{
 const receipt={target_module:'semantic',status:'succeeded'};
 expect(formatMemoryDecision({...receipt,result_status:'current'})).toContain('已保存为当前记忆');
 expect(formatMemoryDecision({...receipt,result_status:'candidate'})).toContain('待确认候选');
 expect(formatMemoryDecision({...receipt,result_status:'disputed'})).toContain('存在冲突');
 expect(formatMemoryDecision(receipt)).toContain('状态未记录');
 expect(formatMemoryDecision({...receipt,status:'failed'})).toContain('写入失败');
});
