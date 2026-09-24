import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Hosts the dev server answers to besides localhost. Vite rejects any other
// Host header outright ("Blocked request. This host ... is not allowed"), which
// is what a tunnel or a LAN hostname hits. Set VITE_ALLOWED_HOSTS in the repo
// root .env to a comma-separated list — ops/local.py injects it into the Vite
// process. Never set this to `true`: that accepts every Host header and opens
// the dev server up to DNS-rebinding.
const allowedHosts = (process.env.VITE_ALLOWED_HOSTS ?? "")
  .split(",")
  .map((host) => host.trim())
  .filter(Boolean);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    allowedHosts,
    // Dev-server parity with the Nginx config that serves the built SPA, so a
    // clickjacking or MIME-sniffing regression shows up locally instead of only
    // in the container. The production policy lives in nginx.conf.
    headers: {
      "X-Frame-Options": "DENY",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      "Content-Security-Policy": "frame-ancestors 'none'"
    },
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true }
    }
  }
});
