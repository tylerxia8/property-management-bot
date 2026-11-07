import type { NextConfig } from "next";

const demoSample = process.env.NEXT_PUBLIC_DEMO_FIXTURE === "sample";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    if (!demoSample) return [];
    return [{ source: "/v1/:path*", destination: "http://api:8000/v1/:path*" }];
  },
};

export default nextConfig;
