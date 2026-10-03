import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发时前端 5173，后端 FastAPI 8000；/api 代理到后端（前端永远只通过 /api 取数）
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  test: { environment: "node", include: ["src/**/*.test.ts"], exclude: ["**/._*", "**/node_modules/**"] },
});
