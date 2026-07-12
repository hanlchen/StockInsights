/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Proxy /api/* to the FastAPI backend so the frontend can call same-origin
    // paths in the browser (avoids CORS entirely in local dev). Backend URL
    // is configurable via BACKEND_URL for non-default setups.
    const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
