export const types = {
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
  working: {
    label: "工作记忆",
    description: "短时任务与临时信息",
    color: "#cfb781",
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
  KEEP_SESSION_ONLY: "保留工作记忆",
  REINFORCE: "强化已有记忆",
  CANDIDATE: "发现候选证据",
  CONSOLIDATE: "完成证据巩固",
  RETRIEVE: "检索记忆",
  RETENTION: "检查保留度",
  USER_DELETE: "删除记忆",
  DROP_PRIVACY: "隐私门拦截",
};
export const decisionNames = {
  WRITE_CURRENT: "已保存为当前记忆",
  KEEP_SESSION_ONLY: "已保留在工作层",
  REINFORCED: "已强化已有记忆",
  CANDIDATE: "已进入候选区，等待更多一致证据",
  CONSOLIDATED: "证据已巩固，当前状态已更新",
  DROP: "未保存：请检查隐私标签与保存同意",
};
export const formatDate = (value) =>
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
