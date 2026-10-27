import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";
import path from "node:path";

export default function nextConfig(phase: string): NextConfig {
  return {
    skipMiddlewareUrlNormalize: true,
    async rewrites() {
      const backend = (
        process.env.BACKEND_URL ||
        process.env.NEXT_PUBLIC_API_URL ||
        "http://127.0.0.1:8060"
      ).replace(/\/$/, "");
      return [
        {
          source: "/ws/terminal/:projectId",
          destination: `${backend}/ws/terminal/:projectId`,
        },
      ];
    },
    allowedDevOrigins: ["10.201.21.211", "100.113.158.66"],
    // Each dev server and production build must own its manifests and cache.
    distDir:
      process.env.NEXT_DIST_DIR ||
      (phase === PHASE_DEVELOPMENT_SERVER
        ? `.next-dev-${process.env.PORT || "3000"}`
        : ".next-build"),
    turbopack: { root: path.resolve(__dirname) },
  };
}
