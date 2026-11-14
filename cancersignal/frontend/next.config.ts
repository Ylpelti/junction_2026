import type { NextConfig } from "next";

// Keep API requests on the public frontend origin. Next.js proxies them to
// FastAPI, so the browser doesn't need cross-origin access. Local development
// defaults to localhost; Render sets NEXT_PUBLIC_API_URL to the API service URL.
const backendOrigin = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${backendOrigin}/api/v1/:path*` },
      { source: "/health", destination: `${backendOrigin}/health` },
    ];
  },
};

export default nextConfig;
