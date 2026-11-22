import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// The service worker caches the app shell so a downloaded chapter opens after a restart with no network.
// Chapter content itself lives in IndexedDB (text) and Cache Storage (audio/page assets), see src/lib/db.ts.
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      workbox: { globPatterns: ['**/*.{js,css,html,woff2,svg}'], navigateFallback: '/index.html', navigateFallbackDenylist: [/^\/api\//] },
      manifest: {
        name: 'Pathya textbook reader',
        short_name: 'Pathya',
        description: 'Accessible English and Hindi textbook reader',
        theme_color: '#f4f1ea',
        background_color: '#f4f1ea',
        display: 'standalone',
        icons: [{ src: '/mark.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' }],
      },
    }),
  ],
})
