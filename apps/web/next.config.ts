import type { NextConfig } from "next";

const API = process.env.API_URL || "http://127.0.0.1:8101";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

export default nextConfig;
