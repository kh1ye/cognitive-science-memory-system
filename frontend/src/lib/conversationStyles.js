// Conversation-only overrides; personal facts always come from the server profile.
export const conversationStyles = [
  { id: "daily", title: "日常陪伴", icon: "chat", description: "轻松交流，关注日常生活与兴趣。", instruction: "请采用自然、温和、简洁的交流方式，优先关注我的日常生活与兴趣。" },
  { id: "work", title: "专注工作", icon: "layers", description: "先给结论，再提供清晰可执行的步骤。", instruction: "请先给结论，再给可执行的步骤。表达简洁，明确区分已知信息与需要确认的事项。" },
  { id: "study", title: "学习探索", icon: "book", description: "循序渐进，用例子帮助理解。", instruction: "请循序渐进地解释，结合具体例子，必要时通过提问确认我的理解。" },
];
export function chatStyle(chat) {
  return conversationStyles.find(style => style.id === chat?.preference_profile)
    || conversationStyles.find(style => chat?.preference_context?.includes(`## 当前场景：${style.title}\n${style.instruction}`));
}
export function chatStyleContext(chat) {
  const style = chatStyle(chat);
  return style ? `## 当前场景：${style.title}\n${style.instruction}` : "";
}
