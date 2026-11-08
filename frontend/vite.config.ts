import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 8321,
    strictPort: true,
    host: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8320", changeOrigin: true },
    },
  },
});
