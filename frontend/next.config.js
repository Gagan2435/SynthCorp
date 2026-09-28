/** @type {import('next').NextConfig} */
// The browser only ever talks to this Next.js server; /api/* is forwarded to FastAPI.
// That avoids CORS entirely. BACKEND_URL is read at build time (see the Dockerfile).
const backend = process.env.BACKEND_URL || "http://localhost:8000";

module.exports = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};
