import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// All data flows through the FastAPI backend — the dev server just proxies
// /api so the browser never needs to know about Supabase or any keys.
// The backend address comes from VITE_API_URL (env var or frontend/.env*);
// it must match the backend PORT (default 8787).
export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), ''), ...process.env }
  const apiUrl = env.VITE_API_URL || 'http://localhost:8787'
  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        '/api': apiUrl,
      },
    },
  }
})
