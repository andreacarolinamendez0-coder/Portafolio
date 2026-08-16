import type { NextConfig } from "next";

const FLASK_URL = process.env.FLASK_URL || "http://localhost:5000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${FLASK_URL}/api/:path*`,
      },
      {
        source: "/telegram-webhook",
        destination: `${FLASK_URL}/telegram-webhook`,
      },
      {
        source: "/demo",
        destination: `${FLASK_URL}/demo`,
      },
    ];
  },
};

export default nextConfig;
