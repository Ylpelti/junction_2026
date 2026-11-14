import type { NextConfig } from "next";

// Keep API requests on the public frontend origin. On Render, Next.js proxies
// them over the private network to FastAPI; local development defaults to
// localhost:8000. This avoids exposing the backend's private hostname or
// relying on cross-origin browser requests.
const backendHostport = process.env.CANCERSIGNAL_API_INTERNAL_HOSTPORT;
const backendOrigin = backendHostport
  ? `http://${backendHostport}`
  : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${backendOrigin}/api/v1/:path*` },
      { source: "/health", destination: `${backendOrigin}/health` },
    ];
  },
};

export default nextConfig;
