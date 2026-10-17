import { defineConfig } from "vite";

export default defineConfig({
  root: "client",
  envDir: "..",
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 6000 },
  server: {
    port: 5173,
    // Discord loads the Activity through a tunnel (e.g. cloudflared), whose host name varies.
    allowedHosts: true,
    proxy: { "/api": "http://localhost:3001", "/interactions": "http://localhost:3001" },
    // Through an https tunnel the hot-reload socket must use port 443.
    hmr: process.env.TUNNEL === "1" ? { clientPort: 443 } : undefined,
  },
});
