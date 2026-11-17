import type { NextConfig } from "next";

// The app is a client of the Silsila API (NEXT_PUBLIC_API_URL). Pages fetch
// on the client with the signed-in user's token, so no server data caching.
// Security headers on every page. No Content-Security-Policy yet: the app has inline styles/scripts and a
// policy needs testing against the real API origin before it can be enforced.
const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // microphone stays available to the app itself (voice intake); everything else is off
  { key: "Permissions-Policy", value: "microphone=(self), camera=(), geolocation=(), payment=()" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
];

const nextConfig: NextConfig = {
  // Minimal self-contained server for the container image (web/Dockerfile).
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
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
