import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/finance/:path*",
        destination: `${process.env.FINANCE_SERVICE_URL || "http://127.0.0.1:8001"}/:path*`,
      },
      {
        source: "/api/scheduling/:path*",
        destination: `${process.env.SCHEDULING_SERVICE_URL || "http://127.0.0.1:8002"}/:path*`,
      },
      {
        source: "/api/risk/:path*",
        destination: `${process.env.RISK_SERVICE_URL || "http://127.0.0.1:8000"}/:path*`,
      },
      {
        source: "/api/mcp/:path*",
        destination: `${process.env.MCP_SERVER_URL || "http://127.0.0.1:8003"}/:path*`,
      },
    ];
  },
  compress: true,
  poweredByHeader: false,
  reactStrictMode: true,
};

export default nextConfig;