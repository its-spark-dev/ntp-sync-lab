import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Rewrite Origin along with Host for FastAPI's same-origin local boundary.
// One fixed loopback upstream; never forward browser-supplied destinations.
const proxy = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
    configure(server: import('vite').HttpProxy.ProxyServer) {
      server.on('proxyReq', (req, original) => {
        if (original.headers.origin === `http://${original.headers.host}`)
          req.setHeader('origin', 'http://127.0.0.1:8000');
      });
    },
  },
};
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy,
    cors: false,
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
    proxy,
    cors: false,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
