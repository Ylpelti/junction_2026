import type { NextConfig } from "next";

const configuredApiOrigin = process.env.NEXT_PUBLIC_API_URL?.trim();
const backendOrigin = (configuredApiOrigin || (
  process.env.NODE_ENV === "production"
    ? "https://cancersignal-api.onrender.com"
    : "http://localhost:8000"
)).replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${backendOrigin}/api/v1/:path*` },
      { source: "/health", destination: `${backendOrigin}/health` },
    ];
  },
};

export default nextConfig;
