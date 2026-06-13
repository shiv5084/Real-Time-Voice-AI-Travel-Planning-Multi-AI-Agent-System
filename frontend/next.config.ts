import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // Allow the backend origin as a trusted image source if needed later
  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname:  "localhost",
      },
    ],
  },

  // Pin Turbopack workspace root to the frontend folder so Next.js doesn't
  // detect the parent repo's package-lock.json and emit the multiple-lockfiles warning.
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;

