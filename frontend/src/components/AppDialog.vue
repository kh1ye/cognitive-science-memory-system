<script setup>
import { ref, watch, onMounted, nextTick, useId } from "vue";
const props = defineProps({
  open: Boolean,
  title: { type: String, default: "" },
});
const emit = defineEmits(["update:open"]);
const element = ref(null);
const titleId = useId();
async function sync() {
  await nextTick();
  if (!element.value) return;
  if (props.open && !element.value.open) element.value.showModal();
  else if (!props.open && element.value.open) element.value.close();
}
watch(() => props.open, sync);
onMounted(sync);
</script>
<template>
  <dialog
    ref="element"
    :aria-labelledby="titleId"
    @cancel.prevent="emit('update:open', false)"
  >
    <div class="dialog-heading">
      <h2 :id="titleId">{{ title }}</h2>
      <button
        type="button"
        class="icon-button"
        aria-label="关闭"
        @click="emit('update:open', false)"
      >
        ×
      </button>
    </div>
    <slot />
  </dialog>
</template>
