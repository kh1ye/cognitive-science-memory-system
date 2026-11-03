import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { reactive } from 'vue';
import ForgettingView from '../views/ForgettingView.vue';
import { WorkspaceKey } from '../composables/useWorkspace';

let wrapper, workspace;
const memory = (id, content, stability = 20) => ({ id, content, memory_type: 'semantic',
  stability_days: stability, initial_stability_days: 20, retention_probability: Math.exp(-1),
  elapsed_days: 20, evidence_count: stability / 20, write_score: .7, protected: true,
  created_at: '2026-10-01T00:00:00Z', forget_at: '2026-12-01T00:00:00Z' });
const payload = (items = [memory('one', '真实偏好')]) => ({ enabled: true, items, threshold: .3,
  evaluated_at: '2026-11-04T00:00:00Z', summary: { total: items.length, protected: items.length, archive_eligible: 0, average_retention: .5 } });
const response = data => ({ ok: true, json: async () => data });
beforeEach(() => {
  workspace = { state: reactive({ user: 'alice', updatedAt: '' }), notify: vi.fn(), runRetention: vi.fn(), openMemory: vi.fn() };
});
afterEach(() => { wrapper?.unmount(); wrapper = null; vi.unstubAllGlobals(); });
function render() {
  wrapper = mount(ForgettingView, { global: { provide: { [WorkspaceKey]: workspace }, stubs: { RouterLink: true } } });
  return flushPromises();
}

it('renders real parameters and samples the exact exponential curve when inspecting a day', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => response(payload())));
  await render();
  expect(fetch.mock.calls[0][0]).toContain('user_id=alice');
  expect(wrapper.get('[data-testid="retention-curve"]').attributes('d')).toContain('M54.00,28.00');
  expect(wrapper.text()).toContain('真实偏好');
  await wrapper.get('[aria-label="查看指定天数的保持度"]').setValue(20);
  expect(wrapper.get('.forget-scrubber').text()).toContain('36.8%');
  await wrapper.findAll('.forget-period button').find(b => b.text() === '180 天').trigger('click');
  expect(wrapper.get('[aria-label="查看指定天数的保持度"]').attributes('max')).toBe('180');
});

it('selects individual memories and uses their independent stability', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => response(payload([memory('one', '原始记忆'), memory('two', '强化记忆', 40)]))));
  await render();
  await wrapper.findAll('.forget-table td button')[1].trigger('click');
  await wrapper.get('[aria-label="查看指定天数的保持度"]').setValue(20);
  expect(wrapper.get('.forget-selected-content').text()).toBe('强化记忆');
  expect(wrapper.get('.forget-scrubber').text()).toContain('60.7%');
  expect(wrapper.get('[data-testid="retention-curve"]').attributes('d')).not.toBe(wrapper.get('[data-testid="baseline-curve"]').attributes('d'));
  await wrapper.get('[aria-label="搜索遗忘记忆"]').setValue('不存在');
  expect(wrapper.findAll('.forget-table tbody tr')).toHaveLength(0);
});

it('saves the real switch and does not archive on a toggle', async () => {
  vi.stubGlobal('fetch', vi.fn(async (path, options) => response(options?.method === 'PUT' ? { enabled: false } : payload())));
  await render();
  await wrapper.get('[role="switch"]').trigger('click'); await flushPromises();
  const put = fetch.mock.calls.find(([, options]) => options.method === 'PUT');
  expect(put[0]).toBe('/api/retention/settings');
  expect(JSON.parse(put[1].body)).toEqual({ user_id: 'alice', enabled: false });
  expect(wrapper.get('[role="switch"]').attributes('aria-checked')).toBe('false');
  expect(wrapper.get('.forget-chart-note').text()).toContain('理论曲线');
  expect(workspace.runRetention).not.toHaveBeenCalled();
});

it('keeps the previous switch state and explains a failed save', async () => {
  vi.stubGlobal('fetch', vi.fn(async (path, options) => {
    if (options?.method === 'PUT') throw Error('网络断开');
    return response(payload());
  }));
  await render(); await wrapper.get('[role="switch"]').trigger('click'); await flushPromises();
  expect(wrapper.get('[role="switch"]').attributes('aria-checked')).toBe('true');
  expect(workspace.notify).toHaveBeenCalledWith('设置未保存：网络断开');
});

it('shows an honest empty state and never draws illustrative memories as real data', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => response(payload([]))));
  await render();
  expect(wrapper.find('[data-testid="retention-curve"]').exists()).toBe(false);
  expect(wrapper.text()).toContain('从第一段记忆开始');
  await wrapper.findAll('button').find(b => b.text() === '添加记忆').trigger('click');
  expect(workspace.openMemory).toHaveBeenCalled();
});

it('ignores late data from a previous space', async () => {
  const pending = [];
  vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => pending.push(resolve))));
  await render();
  workspace.state.user = 'bob'; await flushPromises();
  pending[1](response(payload([memory('bob', '新空间记忆')]))); await flushPromises();
  pending[0](response(payload([memory('alice', '旧空间记忆')]))); await flushPromises();
  expect(wrapper.text()).toContain('新空间记忆');
  expect(wrapper.text()).not.toContain('旧空间记忆');
});
