import { createRouter, createWebHashHistory } from "vue-router";
import InstallView from "./views/InstallView.vue";
import OverviewView from "./views/OverviewView.vue";
import AssistantView from "./views/AssistantView.vue";
import MemoriesView from "./views/MemoriesView.vue";
import EvolutionView from "./views/EvolutionView.vue";
// Preserve links from the previous vanilla frontend.
if (/^#(overview|assistant|memories)$/.test(location.hash)) {
  history.replaceState(null, "", `#/${location.hash.slice(1)}`);
}
export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/install", name: "install", component: InstallView, meta: { title: "安装与接入" } },
    { path: "/", redirect: "/overview" },
    {
      path: "/overview",
      name: "overview",
      component: OverviewView,
      meta: { title: "系统总览" },
    },
    {
      path: "/assistant",
      name: "assistant",
      component: AssistantView,
      meta: { title: "个人助手" },
    },
    {
      path: "/memories",
      name: "memories",
      component: MemoriesView,
      meta: { title: "记忆管理" },
    },
    {
      path: "/evolution",
      name: "evolution",
      component: EvolutionView,
      meta: { title: "记忆演化" },
    },
    { path: "/:pathMatch(.*)*", redirect: "/overview" },
  ],
});
