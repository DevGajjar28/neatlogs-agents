import type { NextConfig } from "next";

/**
 * Same-origin /api proxy for Vercel → EC2.
 * Set API_UPSTREAM=http://<EC2_PUBLIC_IP>:8000 on Vercel (server-only).
 * Set NEXT_PUBLIC_API_BASE=/api so the browser never hits http://EC2 (mixed content).
 * Locally leave API_UPSTREAM unset and use NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000/api.
 */
const apiUpstream = (process.env.API_UPSTREAM || "").replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    if (!apiUpstream) {
      return [];
    }
    return [
      {
        source: "/api/:path*",
        destination: `${apiUpstream}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
