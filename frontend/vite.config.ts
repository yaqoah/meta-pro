import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  optimizeDeps: {
    exclude: ['lucide-react'],
  },
  server: {
    // host: true + fixed port so GitHub Codespaces (and other port
    // forwards) can expose the dev server.
    host: true,
    port: 5173,
    proxy: {
      // Dev-only: forward API + SSE traffic to the FastAPI backend.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false, // tolerate self-signed certs on the backend target
      },
    },
  },
});
