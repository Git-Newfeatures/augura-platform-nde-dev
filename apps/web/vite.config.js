import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  build: {
    // Découpe les grosses dépendances en chunks séparés (sinon un seul bundle ~1 Mo).
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('react-dom') || id.includes('/react/') || id.includes('react-router'))
            return 'react'
          if (id.includes('@supabase')) return 'supabase'
          if (id.includes('lucide-react') || id.includes('radix-ui')) return 'ui'
          return 'vendor'
        },
      },
    },
  },
  server: {
    proxy: {
      // Forward /api/* to a sibling `vercel dev` instance.
      '/api': {
        target: 'http://localhost:3001',
        changeOrigin: true,
      },
    },
  },
})
