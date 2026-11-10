import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5174,
    proxy: {
      // 本地后端使用18000，避开当前Windows环境不可绑定的8000端口。
      "/api": {
        target: "http://127.0.0.1:18000",
        changeOrigin: true,
      },
    },
  },
});
