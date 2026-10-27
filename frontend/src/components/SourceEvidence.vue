<script setup>
import { onUnmounted, ref, watch } from "vue";
import { api } from "../lib/api";
import { formatDate } from "../lib/format";
const props = defineProps({ memoryId: String, userId: String });
const result = ref(null), loading = ref(false), error = ref("");
let version = 0;
watch(() => [props.memoryId, props.userId], async ([id, user]) => {
  const request = ++version;
  result.value = null; error.value = "";
  if (!id || !user) return;
  loading.value = true;
  try {
    const data = await api(`/api/memories/${encodeURIComponent(id)}/evidence?user_id=${encodeURIComponent(user)}`);
    if (request === version) result.value = data;
  } catch (failure) {
    if (request === version) error.value = failure.message;
  } finally {
    if (request === version) loading.value = false;
  }
}, { immediate: true });
onUnmounted(() => { version++; });
const sourceLink = (item) => `#/assistant?thread=${encodeURIComponent(item.thread_id)}${item.message_id ? `&message=${encodeURIComponent(item.message_id)}` : ""}`;
</script>
<template>
  <section class="source-evidence" aria-label="来源证据">
    <h3>来源证据</h3>
    <p v-if="loading" class="subtle" role="status">正在读取来源…</p>
    <p v-else-if="error" class="error-text" role="alert">{{ error }}</p>
    <template v-else-if="result">
      <p class="form-hint">可查看 {{ result.total_count }} 条来源记录 · 累计证据计数 {{ result.evidence_count }}</p>
      <p v-if="result.legacy_gap" class="memory-notice">历史记录有 {{ result.legacy_gap }} 条计数未保留逐条原文，无法完整回溯。</p>
      <article v-for="item in result.items" :key="item.id" class="source-item">
        <blockquote>{{ item.content }}</blockquote>
        <p class="subtle">{{ item.source }} · {{ item.created_at ? formatDate(item.created_at) : '时间未记录' }}</p>
        <p v-if="item.legacy" class="form-hint">从历史记录恢复的已知来源；不代表全部历史证据。</p>
        <a v-if="item.thread_id" class="text-button" :href="sourceLink(item)">{{ item.message_id ? '查看原始消息' : '查看来源会话' }} ↗</a>
        <small v-else class="subtle">未记录来源会话</small>
      </article>
      <p v-if="result.total_count > result.items.length" class="form-hint">当前显示 {{ result.items.length }} 条来源，合计 {{ result.total_count }} 条。</p>
    </template>
  </section>
</template>
<style scoped>
.source-evidence { margin-top:24px; border-top:1px solid var(--line); padding-top:16px; }
h3 { font-size:14px; margin:0 0 10px; }
.source-item { border:1px solid var(--line); border-radius:7px; padding:12px; margin-top:10px; }
blockquote { margin:0 0 8px; font-size:13px; line-height:1.8; white-space:pre-wrap; overflow-wrap:anywhere; }
.source-item a { margin-top:10px; }
</style>
