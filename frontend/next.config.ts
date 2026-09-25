import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Next.js's dev server blocks cross-origin access to its own dev
  // resources (HMR websocket, /_next/* assets) from any host not on this
  // list — "localhost" is allowed by default but "127.0.0.1" is not,
  // even though they're the same machine. Without this, loading the app
  // via 127.0.0.1 silently breaks the client runtime (HMR socket refused
  // with 403), which in turn breaks React hydration/interactivity —
  // exactly what caused the login form to fall back to a native,
  // non-JS submission. Only affects `next dev`; irrelevant in production.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
