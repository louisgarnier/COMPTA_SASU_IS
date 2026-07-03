import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // Proxy : le front sert d'entrée unique (joignable en LAN sur :3001) et relaie
  // les appels /api vers le backend local (127.0.0.1:8001, souvent lié à localhost
  // uniquement). Le navigateur — Mac ou téléphone — n'appelle donc que le front,
  // même origine → pas de CORS, pas besoin d'exposer le backend sur le réseau.
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://127.0.0.1:8001/api/:path*',
      },
    ];
  },
};

export default nextConfig;




