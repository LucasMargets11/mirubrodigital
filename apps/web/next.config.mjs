const isDev = process.env.NODE_ENV === 'development';

const nextConfig = {
  reactStrictMode: true,
  images: {
    // Allow local dev API and the internal Docker service name for SSR image optimisation.
    // In production the browser always gets the public domain; api:8000 is never exposed.
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'via.placeholder.com',
      },
      {
        protocol: 'https',
        hostname: 'images.unsplash.com',
      },
      {
        protocol: 'http',
        hostname: 'localhost',
        port: '8000',
      },
      // Internal Docker Compose hostname – only used during SSR image optimisation,
      // never sent to the browser (buildMediaUrl rewrites it to the public URL first).
      ...(isDev
        ? [
            {
              protocol: 'http',
              hostname: 'api',
              port: '8000',
            },
          ]
        : []),
    ],
  },
  experimental: {
    typedRoutes: true,
  },
};

export default nextConfig;
