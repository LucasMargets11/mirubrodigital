const isDev = process.env.NODE_ENV === 'development';

// Production API hostname for next/image remote patterns.
// Set API_HOSTNAME in the build environment (e.g. "api.mirubro.com").
const apiHostname = process.env.API_HOSTNAME || '';

const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  images: {
    // Allow SVG images from the public directory (used for blog covers).
    dangerouslyAllowSVG: true,
    contentDispositionType: 'attachment',
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
      // Production API hostname (set via API_HOSTNAME env var at build time)
      ...(apiHostname
        ? [
            {
              protocol: 'https',
              hostname: apiHostname,
            },
          ]
        : []),
      // Dev-only: local API server
      ...(isDev
        ? [
            {
              protocol: 'http',
              hostname: 'localhost',
              port: '8000',
            },
          ]
        : []),
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
  typedRoutes: true,
};

export default nextConfig;
