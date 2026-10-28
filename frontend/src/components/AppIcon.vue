<script setup>
defineProps({ name: { type: String, default: "memory" } });
const icons = {
  constellation: '<circle cx="5" cy="7" r="2"/><circle cx="18" cy="4" r="1.5"/><circle cx="14" cy="15" r="2.5"/><circle cx="4" cy="20" r="1"/><circle cx="21" cy="20" r="1"/><path d="m7 7 9-3M6 9l6 5m4 3 4 3M5 19l7-3"/>',
  sidebar: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
  overview:
    '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  chat: '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z"/>',
  memory:
    '<rect x="4" y="3" width="16" height="18" rx="3"/><path d="M8 3v18m4-12h4m-4 4h4"/>',
  activity: '<path d="M3 12h4l3-7 4 14 3-7h4"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
  database:
    '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
  book: '<path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1v15"/>',
  external: '<path d="M14 3h7v7m0-7L10 14m-1-9H4v15h15v-5"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  refresh: '<path d="M20 7a8 8 0 1 0 0 10M20 3v5h-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3m-10 0 1 15h12l1-15M10 10v7m4-7v7"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  arrowUp: '<path d="M12 20V4m-6 6 6-6 6 6"/>',
};
</script>
<template>
  <i
    ><svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      v-html="icons[name] || icons.memory"
    ></svg
  ></i>
</template>
