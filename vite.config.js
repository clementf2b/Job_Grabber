import { defineConfig } from 'vite'

export default defineConfig({
  server: {
    port: 5173,
    open: true,
    proxy: {
      '/jobs':       'http://127.0.0.1:8000',
      '/progress':   {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // SSE requires streaming — disable proxy buffering
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache';
            proxyRes.headers['x-accel-buffering'] = 'no';
          });
        },
      },
      '/scrape-url': 'http://127.0.0.1:8000',
      '/status':     'http://127.0.0.1:8000',
      '/refresh':    'http://127.0.0.1:8000',
      '/cancel':     'http://127.0.0.1:8000',
    },
  },
})
