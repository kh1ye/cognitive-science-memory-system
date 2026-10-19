export function recentChange(event) {
  const details = event.details || {};
  const descriptions = {
    WRITE_CURRENT: "通过价值筛选，写入了一条当前长期记忆。",
    KEEP_SESSION_ONLY: "信息保留在工作层，未进入当前长期记忆；记录仍会持久保存。",
    REINFORCE: details.evidence_count == null
      ? "新增一致证据，强化已有记录，没有重复创建记忆。"
      : `新增一致证据，该记录的证据数在此次操作后为 ${details.evidence_count} 条。`,
    CANDIDATE: "发现与原有当前记忆不一致的新证据，先保存为候选，未在此步骤替换旧记忆。",
    CONSOLIDATE: "证据达到巩固条件，新版本成为当前记忆，旧版本转为历史。",
    DROP_PRIVACY: "隐私检查阻止了写入，本次没有保存记忆正文。",
    USER_DELETE: "按用户要求删除了记忆正文，审计仅保留操作记录。",
    RETRIEVE: Array.isArray(details.result_ids)
      ? `此次检索返回 ${details.result_ids.length} 条记忆证据。`
      : "执行了一次记忆检索。",
    RETENTION: Array.isArray(details.archived_ids)
      ? `完成保留度检查，此次归档 ${details.archived_ids.length} 条记忆。`
      : "完成了一次保留度检查。",
  };
  return descriptions[event.event_type] || event.message || "完成了一次记忆操作。";
}

export function moduleState(module) {
  if (module.name === "语言模型" && module.status === "ready")
    return { label: "已配置", tone: "configured" };
  const states = {
    ready: { label: "已就绪", tone: "ready" },
    configured: { label: "已配置", tone: "configured" },
    unconfigured: { label: "未配置", tone: "off" },
    not_implemented: { label: "暂未实现", tone: "off" },
    unsupported: { label: "配置需检查", tone: "warning" },
  };
  return states[module.status] || { label: "状态未知", tone: "off" };
}
