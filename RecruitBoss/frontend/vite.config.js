import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies /api to the Python backend; `npm run build` writes into backend/static.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  build: { outDir: "../backend/static", emptyOutDir: true },
});
