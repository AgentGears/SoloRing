/** @type {import('next').NextConfig} */
const nextConfig = {
  // Single backend-origin setting (M2 §4.2): consumed here for the browser
  // /api/* rewrite target and by src/lib/api.server.ts for Server Component
  // requests. The legacy SOLORING_API_URL name is removed.
  async rewrites() {
    const api = process.env.SOLORING_API_ORIGIN || "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
};

export default nextConfig;
