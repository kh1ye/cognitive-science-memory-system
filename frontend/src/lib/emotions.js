export const emotionStates = {
  energetic: { emoji: "⚡", title: "元气满满" },
  happy: { emoji: "😄", title: "开心愉快" },
  calm: { emoji: "😌", title: "平静放松" },
  neutral: { emoji: "😐", title: "平平淡淡" },
  tired: { emoji: "😴", title: "有点疲惫" },
  sad: { emoji: "😔", title: "难过低落" },
  anxious: { emoji: "😟", title: "紧张焦虑" },
  irritable: { emoji: "😤", title: "烦躁郁闷" },
};
export const defaultEmotion = () => ({ label: "neutral", confidence: 0, ...emotionStates.neutral });
