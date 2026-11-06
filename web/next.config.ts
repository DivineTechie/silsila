import type { NextConfig } from "next";

// The app is a client of the Silsila API (NEXT_PUBLIC_API_URL). Pages fetch
// on the client with the signed-in user's token, so no server data caching.
const nextConfig: NextConfig = {
  // Minimal self-contained server for the container image (web/Dockerfile).
  output: "standalone",
  poweredByHeader: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
