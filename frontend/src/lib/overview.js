import { t } from "./i18n";

export function recentChange(event) {
  const details = event.details || {};
  const descriptions = {
    WRITE_CURRENT: t("通过价值筛选，写入了一条当前长期记忆。"),
    KEEP_SESSION_ONLY: t("信息保留在工作层，未进入当前长期记忆；记录仍会持久保存。"),
    REINFORCE: details.evidence_count == null
      ? t("新增一致证据，强化已有记录，没有重复创建记忆。")
      : t("新增一致证据，该记录的证据数在此次操作后为 {count} 条。", { count: details.evidence_count }),
    CANDIDATE: t("发现与原有当前记忆不一致的新证据，先保存为候选，未在此步骤替换旧记忆。"),
    CONSOLIDATE: t("证据达到巩固条件，新版本成为当前记忆，旧版本转为历史。"),
    DROP_PRIVACY: t("隐私检查阻止了写入，本次没有保存记忆正文。"),
    USER_DELETE: t("按用户要求删除了记忆正文，审计仅保留操作记录。"),
    RETRIEVE: Array.isArray(details.result_ids)
      ? t("此次检索返回 {count} 条记忆证据。", { count: details.result_ids.length })
      : t("执行了一次记忆检索。"),
    RETENTION: Array.isArray(details.archived_ids)
      ? t("完成保留度检查，此次归档 {count} 条记忆。", { count: details.archived_ids.length })
      : t("完成了一次保留度检查。"),
  };
  return descriptions[event.event_type] || event.message || t("完成了一次记忆操作。");
}

export function moduleState(module) {
  if (module.name === "语言模型" && module.status === "ready")
    return { label: t("已配置"), tone: "configured" };
  const states = {
    ready: { label: t("已就绪"), tone: "ready" },
    configured: { label: t("已配置"), tone: "configured" },
    unconfigured: { label: t("未配置"), tone: "off" },
    not_implemented: { label: t("暂未实现"), tone: "off" },
    unsupported: { label: t("配置需检查"), tone: "warning" },
  };
  return states[module.status] || { label: t("状态未知"), tone: "off" };
}
