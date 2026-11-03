/** @type {import('next').NextConfig} */
// The browser only ever talks to this Next.js server; /api/* is forwarded to FastAPI.
// That avoids CORS entirely. BACKEND_URL is read at build time:
//   - Docker: set by the Dockerfile / docker-compose
//   - Vercel: set it in Project Settings -> Environment Variables (your Render URL)
const backend = (process.env.BACKEND_URL || "http://localhost:8000").replace(/\/+$/, "");

module.exports = {
  // "standalone" is for the Docker image; Vercel does its own packaging.
  ...(process.env.VERCEL ? {} : { output: "standalone" }),
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};
