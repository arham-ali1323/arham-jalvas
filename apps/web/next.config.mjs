/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Standalone output (a self-contained server.js) is only used for the
  // container image; local `next dev`/`next start` are left untouched so the
  // developer workflow does not change. `next build` in Docker sets NEXT_OUTPUT.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  eslint: {
    dirs: ["src"],
  },
};

export default nextConfig;
