import { createApp } from "vue";
import { ElDialog } from "element-plus";
import "element-plus/es/components/dialog/style/css";
import App from "./Platform.vue";
import "./styles/platform.css";

createApp(App).component("ElDialog", ElDialog).mount("#app");
