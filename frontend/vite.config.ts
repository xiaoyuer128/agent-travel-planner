import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 开发环境把 /api 转发到 FastAPI 后端，避免跨域
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});