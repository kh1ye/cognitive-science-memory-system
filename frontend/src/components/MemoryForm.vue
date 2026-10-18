<script setup>
import { ref, watch } from "vue";
import AppDialog from "./AppDialog.vue";
import { useWorkspace } from "../composables/useWorkspace";
const { state, saveMemory } = useWorkspace();
const error = ref(""),
  saving = ref(false);
watch(
  () => state.memoryDraft,
  () => {
    error.value = "";
  },
);
async function submit() {
  if (saving.value || !state.memoryDraft.content.trim()) return;
  saving.value = true;
  error.value = "";
  try {
    await saveMemory({ ...state.memoryDraft });
  } catch (exception) {
    error.value = exception.message;
  } finally {
    saving.value = false;
  }
}
</script>
<template>
  <AppDialog
    :open="!!state.memoryDraft"
    title="添加记忆"
    @update:open="state.memoryDraft = null"
  >
    <form v-if="state.memoryDraft" @submit.prevent="submit">
      <label
        >记忆内容<textarea
          v-model="state.memoryDraft.content"
          required
          rows="4"
          maxlength="10000"
          placeholder="你希望长期记住的事…"
        />
      </label>
      <div class="form-grid">
        <label
          >记忆类型<select v-model="state.memoryDraft.memory_type">
            <option value="semantic">语义记忆</option>
            <option value="episodic">情景记忆</option>
            <option value="procedural">程序记忆</option>
            <option value="working">工作记忆</option>
          </select></label
        >
        <label
          >标签<input
            v-model="state.memoryDraft.tags"
            placeholder="偏好、目标，以逗号分隔"
        /></label>
        <label
          >主题标识<input
            v-model="state.memoryDraft.memory_key"
            placeholder="例如 coding_language"
        /></label>
        <label
          >主题取值<input
            v-model="state.memoryDraft.memory_value"
            placeholder="例如 Python"
        /></label>
      </div>
      <p class="form-hint">
        同一主题的不同取值会参与冲突判断，重复一致的证据可触发巩固。
      </p>
      <label class="checkbox"
        ><input
          v-model="state.memoryDraft.consent"
          type="checkbox"
        />这条信息包含敏感内容，我同意保存</label
      >
      <div class="dialog-actions">
        <span class="error-text" role="alert">{{ error }}</span
        ><button type="button" class="button" @click="state.memoryDraft = null">
          取消</button
        ><button class="button primary" :disabled="saving">
          {{ saving ? "保存中…" : "保存记忆" }}
        </button>
      </div>
    </form>
  </AppDialog>
</template>
