import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import "./styles.css";
import "./dark.css";
import { t } from "./lib/i18n";
const app=createApp(App);
app.config.globalProperties.$t=t;
app.use(router).mount("#app");
