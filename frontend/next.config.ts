import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  skipMiddlewareUrlNormalize: true,
  distDir: process.env.NEXT_DIST_DIR || '.next',
  turbopack: { root: path.resolve(__dirname) },
};

export default nextConfig;
