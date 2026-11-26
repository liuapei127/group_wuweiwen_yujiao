import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
const apiTarget = process.env.ENT_DEV_API_URL || 'http://127.0.0.1:8002'
const proxy = {
  '/api': {target: apiTarget, changeOrigin: true},
  '/health': {target: apiTarget, changeOrigin: true},
}
export default defineConfig({
  plugins: [react()],
  server: {host: '127.0.0.1', port: 5173, strictPort: true, proxy},
  preview: {host: '127.0.0.1', port: 5173, strictPort: true, proxy},
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('@ant-design/icons')) return 'vendor-icons'
          if (id.includes('antd') || id.includes('@ant-design') || id.includes('rc-')) return 'vendor-antd'
          if (id.includes('@tanstack/react-query')) return 'vendor-query'
          if (id.includes('react-router')) return 'vendor-router'
          if (id.includes('react-dom') || id.includes('/react/') || id.includes('\\react\\')) return 'vendor-react'
        },
      },
    },
  },
})
