import type { NextConfig } from "next";

const demoSample = process.env.NEXT_PUBLIC_DEMO_FIXTURE === "sample";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: { proxyClientMaxBodySize: "210mb", proxyTimeout: 120_000 },
  async rewrites() {
    if (!demoSample) return [];
    const origin = process.env.API_INTERNAL_ORIGIN ?? "http://api:8000";
    return [{ source: "/v1/:path*", destination: `${origin}/v1/:path*` }];
  },
};

export default nextConfig;
