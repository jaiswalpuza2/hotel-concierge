/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required by the production Dockerfile (copies .next/standalone).
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
};

export default nextConfig;
