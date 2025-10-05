// vite.config.ts
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'

export default defineConfig(({ mode }) => {
  // Load env from project root, not frontend folder
  const env = loadEnv(mode, path.resolve(__dirname, '..'), '')
  
  // Check if we're in production build mode
  const isProduction = mode === 'production'
  
  // SSL configuration - only for development
  const sslConfig = !isProduction && fs.existsSync(path.resolve(__dirname, 'cert/key.pem')) ? {
    https: {
      key: fs.readFileSync(path.resolve(__dirname, 'cert/key.pem')),
      cert: fs.readFileSync(path.resolve(__dirname, 'cert/cert.pem')),
    },
  } : {}
  
  return {
  envDir: path.resolve(__dirname, '..'), // Load .env from project root
  plugins: [react()],
  server: {
    ...sslConfig,
    host: true,
    port: parseInt(env.VITE_DEV_PORT || '5173'),
    hmr: false, // Отключаем HMR
    watch: {
      usePolling: true, // Принудительное отслеживание файлов
      interval: 1000
    },
    allowedHosts: ['homecakes.site', 'localhost', '127.0.0.1'],
    proxy: {
      '/api': {
        target: env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  },
  build: {
    // Production optimizations
    target: 'es2020',
    minify: 'terser',
    sourcemap: false,
    cssCodeSplit: true,
    
    rollupOptions: {
      output: {
        // Code splitting for better caching
        manualChunks: {
          vendor: ['react', 'react-dom'],
          telegram: ['@telegram-apps/sdk-react'],
          ui: ['react-router-dom', 'zustand'],
          charts: ['chart.js', 'react-chartjs-2', 'recharts'],
          i18n: ['i18next', 'react-i18next']
        },
        // Optimized file naming
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]'
      }
    },
    
    // Build performance
    chunkSizeWarningLimit: 600,
    
    // Compression settings
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
        pure_funcs: ['console.log', 'console.info']
      }
    }
  },
  
  // Optimization settings
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      '@telegram-apps/sdk-react',
      'react-router-dom',
      'zustand',
      'i18next',
      'react-i18next'
    ]
  },
}})
