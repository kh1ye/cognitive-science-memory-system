import { roles } from "./format";

export function decisionSummary(trace) {
  const decision = trace.result.decision;
  if (decision === "CANDIDATE")
    return "发现新的不一致证据，已保存为候选；原有当前记忆暂时保留。";
  if (decision === "CONSOLIDATED")
    return "新证据达到巩固条件，新记忆成为当前；旧记忆已转为历史。";
  if (decision === "REINFORCED")
    return "本次信息与已有记录一致，已增加证据并强化记录，没有重复新建。";
  if (decision === "KEEP_SESSION_ONLY")
    return "本次信息保留在工作层，未成为当前长期记忆；工作层记录仍会持久保存。";
  if (decision === "DROP")
    return trace.result.reason === "consent_required"
      ? "本次包含需要明确同意的敏感信息，已拦截，未保存正文。"
      : "识别到不记忆指令，已停止写入，没有保存正文。";
  return "本次信息通过筛选，已保存为当前长期记忆。";
}

export function evidenceParts(content, candidates) {
  const ranges = candidates.flatMap((candidate, index) => {
    if (!candidate.content) return [];
    const start = content.indexOf(candidate.content);
    return start < 0 ? [] : [{ start, end: start + candidate.content.length, index }];
  });
  const boundaries = [...new Set([0, content.length, ...ranges.flatMap((range) => [range.start, range.end])])].sort((left, right) => left - right);
  return boundaries.slice(0, -1).map((start, index) => {
    const end = boundaries[index + 1];
    const matches = ranges.filter((range) => range.start <= start && range.end >= end);
    return {
      text: content.slice(start, end),
      highlighted: matches.length > 0,
      label: matches.map((range) => `候选 ${range.index + 1} 的原文证据`).join("、"),
    };
  });
}

export function afterState(trace) {
  const record = trace.result.memory;
  const previous = trace.previous;
  const decision = trace.result.decision;
  const items = [];
  if (previous && (decision === "CANDIDATE" || decision === "CONSOLIDATED" || decision === "WRITE_CURRENT")) {
    items.push({
      content: previous.content,
      role: decision === "CONSOLIDATED" ? "历史" : roles[previous.state_role]?.label || previous.state_role,
    });
  }
  if (record) items.push({ content: record.content, role: roles[record.state_role]?.label || record.state_role });
  return items;
}

export function metricExplanation(field, trace) {
  const config = trace.config || {};
  const gate = trace.result.gate || {};
  const fields = trace.steps.flatMap((step) => step.fields);
  const number = Number(field.value);
  const valueFor = (label) => fields.find((item) => item.label === label)?.value;
  if (field.label === "写入分数") {
    const threshold = config.write_threshold ?? valueFor("写入门槛");
    if (threshold == null) return "综合重要性、置信度、画像重合及噪声惩罚得到，不等于写入概率。";
    return number >= threshold
      ? `达到写入门槛 ${threshold}；是否更新当前记忆还需检查类型与证据。`
      : `低于写入门槛 ${threshold}，本次信息保留在工作层。`;
  }
  if (field.label === "写入门槛") return "进入长期记忆处理的最低写入分数，不代表巩固条件已满足。";
  if (field.label === "预测误差") {
    const threshold = config.cpe_commit_threshold ?? gate.commit_threshold ?? valueFor("巩固误差门槛");
    return threshold == null
      ? "表示本次新旧信息的差异程度，不是模型回答错误的概率。"
      : `${number >= threshold ? "达到" : "尚未达到"}巩固误差门槛 ${threshold}；仍需同时满足证据数量和一致性要求。`;
  }
  if (field.label === "一致证据数量") {
    const minimum = config.minimum_evidence_count ?? gate.minimum_evidence_count ?? valueFor("最低证据数量");
    return minimum == null ? "本次处理时累计的同一新取值证据数量。"
      : `累计 ${number} 条，需要至少 ${minimum} 条；${number >= minimum ? "数量条件已满足，仍需检查其他条件" : "数量尚不足，等待后续真实输入"}。`;
  }
  if (field.label === "证据一致性") {
    const threshold = config.evidence_consistency_threshold ?? gate.consistency_threshold ?? valueFor("一致性门槛");
    return threshold == null ? "衡量候选证据之间是否一致，单条证据的一致性不能代替数量要求。"
      : `${number >= threshold ? "达到" : "尚未达到"}一致性门槛 ${threshold}；单条证据即使一致，也不能代替数量要求。`;
  }
  const explanations = {
    显著性: "由输入重要性与关键提示词计算；不直接代表写入概率。",
    任务相关性: "反映与当前任务目标的相关程度；未提供目标时使用默认值 0.5。",
    偏好强度: "由同主题记录数量与偏好标签共同影响，是规则分数。",
    注意偏向: "综合显著性、任务相关性和偏好强度，用于注意力调制。",
    巩固误差门槛: "需要与最低证据数量、一致性门槛同时满足。",
    最低证据数量: "需要后续真实输入提供证据，系统不会自动生成确认。",
    一致性门槛: "只有足够且一致的证据，才能支持更新当前记忆。",
    决策代码: "原记忆引擎返回的实际分支标识。",
    原因代码: "该分支的实际触发原因；不代表额外执行了模型推理。",
  };
  return explanations[field.label] || "";
}
