import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import zhCn from "element-plus/es/locale/lang/zh-cn";

import App from "./App.vue";
import { router } from "./router";

// 样式顺序：先 Element Plus 定制主题，后自有 Design Tokens
import "./styles/element-theme.scss";
import "./styles/tokens.scss";

const app = createApp(App);

app.use(createPinia());
app.use(router);
app.use(ElementPlus, { locale: zhCn });

app.mount("#app");
