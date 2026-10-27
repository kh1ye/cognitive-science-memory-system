export const types = {
  working: { label: "工作记忆", description: "当前任务状态与临时约束", color: "#b6a6ca" },
  semantic: {
    label: "语义记忆",
    description: "事实、偏好与个人画像",
    color: "#6384c8",
  },
  episodic: { label: "情景记忆", description: "经历与事件", color: "#81a692" },
  procedural: {
    label: "程序记忆",
    description: "方法、流程与习惯",
    color: "#b5a3c9",
  },
};
export const roles = {
  current: { label: "当前", color: "#6689c9" },
  candidate: { label: "候选", color: "#d1b174" },
  history: { label: "历史", color: "#9aaacc" },
  working: { label: "工作层", color: "#b6a6ca" },
  archived: { label: "已归档", color: "#d6dce5" },
};
export const eventNames = {
  WRITE_CURRENT: "写入长期记忆",
  KEEP_SESSION_ONLY: "保留在工作层",
  REINFORCE: "强化已有记忆",
  UNCHANGED: "来源事件已处理",
  CANDIDATE: "发现候选证据",
  CONSOLIDATE: "完成证据巩固",
  RETRIEVE: "检索记忆",
  RETENTION: "检查保留度",
  USER_DELETE: "删除记忆",
  DROP_PRIVACY: "隐私门拦截",
  TYPED_LEARNING: "四类记忆写入",
};
export const decisionNames = {
  WRITE_CURRENT: "已保存为当前记忆",
  KEEP_SESSION_ONLY: "已保留在工作层",
  REINFORCED: "已强化已有记忆",
  UNCHANGED: "该来源已处理，未重复增加证据",
  CANDIDATE: "已进入候选区，等待更多一致证据",
  CONSOLIDATED: "证据已巩固，当前状态已更新",
  DROP: "未保存：请检查隐私标签与保存同意",
};
export const memoryStatusNames = {
  disabled: "自动记忆已关闭，本轮仅保留会话记录",
  no_new_memory: "本轮未发现需要长期保存的新信息",
  privacy_blocked: "遵循不记忆指令，本轮未写入长期记忆",
  failed: "本轮自动记忆处理失败，信息尚未确认加入",
};
export function formatMemoryDecision(result) {
  if (result.target_module) return `${types[result.target_module]?.label || result.target_module}：${result.status === 'succeeded' ? '已写入' : '写入失败'}`;
  if (result.reason === "no_source_evidence") return "未写入：提取内容没有原话依据";
  if (result.reason === "consent_required") return "未写入：敏感信息需要手动确认同意";
  return decisionNames[result.decision] || result.decision;
}
export const formatDate = (value) => !value || !Number.isFinite(new Date(value).getTime()) ? "未记录" :
  new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
export function age(value) {
  const seconds = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000);
  return seconds < 60
    ? "刚刚"
    : seconds < 3600
      ? `${Math.floor(seconds / 60)} 分钟前`
      : seconds < 86400
        ? `${Math.floor(seconds / 3600)} 小时前`
        : formatDate(value);
}
export function bytes(value) {
  return value < 1024
    ? `${value} B`
    : value < 1048576
      ? `${(value / 1024).toFixed(1)} KB`
      : `${(value / 1048576).toFixed(2)} MB`;
}
