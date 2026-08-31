import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import AutoImport from 'unplugin-auto-import/vite'

// https://vite.dev/config/
export default defineConfig({
  server: {
    host: '0.0.0.0', // Allow access from other devices on LAN
    port: 5001,
    // Allow the Tailscale MagicDNS domain so the phone can reach the dev server
    // over the private tailnet (Vite blocks unknown Host headers by default).
    // Plain 100.x Tailscale IPs are allowed automatically; this covers the
    // friendlier *.ts.net hostnames.
    allowedHosts: ['.ts.net'],
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:50001',
        changeOrigin: true,
      },
      '/cypress': {
        target: 'http://127.0.0.1:50001',
        changeOrigin: true,
      },
      '/socket.io': {
        target: 'http://127.0.0.1:50001',
        ws: true,
      },
    },
  },
  plugins: [
    vue(),
    vueDevTools(),
    AutoImport({
      resolvers: [ElementPlusResolver()],
    }),
    Components({
      resolvers: [ElementPlusResolver()],
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
})
