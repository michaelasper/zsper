const brainApiBaseUrl = (
  process.env.NEXT_PUBLIC_BRAIN_API_BASE_URL ?? "http://brain-api:8000"
).replace(/\/$/, "");

/** @type {import("next").NextConfig} */
const nextConfig = {
  devIndicators: false,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${brainApiBaseUrl}/api/:path*`
      }
    ];
  }
};

export default nextConfig;
