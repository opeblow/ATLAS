import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export so the dashboard deploys to Cloudflare Pages (or any static
  // host) with no Node runtime. Every data fetch is client-side, so nothing
  // here needs a server. See docs/deployment.md.
  output: "export",
  // Emit /page.html so the static host serves clean URLs (/money, not /money/).
  trailingSlash: true,
  images: { unoptimized: true },
  compress: true,
  poweredByHeader: false,
  reactStrictMode: true,
};

export default nextConfig;