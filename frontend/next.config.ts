import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep production health-check builds from replacing the asset manifest used
  // by a running development server. Sharing `.next` between `next dev` and
  // `next build` leaves the browser with HTML that points to missing bundles.
  distDir: process.env.NODE_ENV === "production" ? ".next-build" : ".next",
  allowedDevOrigins: process.env.TAILSCALE_HOSTNAME
    ? [process.env.TAILSCALE_HOSTNAME]
    : [],
};

export default nextConfig;
