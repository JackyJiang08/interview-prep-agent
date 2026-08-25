import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev mode proxies the API and the socket to a locally running
// `interview-prep-agent serve`; the production build is static assets the
// server mounts itself.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", ws: true },
    },
  },
});
