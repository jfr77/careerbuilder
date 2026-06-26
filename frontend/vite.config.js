import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// In local dev the dev server proxies /api to the backend (VITE_API_URL), so
// the browser never needs the backend's address. In a GitHub Pages build the
// frontend instead calls VITE_API_URL directly (cross-origin) and there is no
// proxy — see src/api.js.
//
// base: GitHub Pages project sites serve under /<repo>/, so the built asset
// paths must be prefixed. Set VITE_BASE=/<repo>/ for the Pages build; it stays
// '/' for local dev and root-domain hosting.
export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), ''), ...process.env }
  const apiUrl = env.VITE_API_URL || 'http://localhost:8787'
  return {
    base: env.VITE_BASE || '/',
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        '/api': apiUrl,
      },
    },
  }
})
