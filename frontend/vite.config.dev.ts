// vite.config.dev.ts - конфигурация для тестирования без HTTPS
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  // Load env from project root, not frontend folder
  const env = loadEnv(mode, path.resolve(__dirname, '..'), '')
  
  return {
  envDir: path.resolve(__dirname, '..'), // Load .env from project root
  plugins: [react()],
  server: {
    host: true,
    port: parseInt(env.VITE_DEV_PORT || '5173'),
    hmr: false,
    allowedHosts: ['que-crash.fun', 'localhost', '127.0.0.1', 'frontend'],
    watch: {
      usePolling: true,
      interval: 500
    },
    proxy: {
      '/api': {
        target: env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  },
  build: {
    // 🚀 КРИТИЧНО: Базовая оптимизация для 100 Мбит канала
    target: 'es2020',
    minify: true, // Используем встроенный минификатор esbuild
    sourcemap: false, // Убираем sourcemap в проде для экономии
    cssCodeSplit: true,
    chunkSizeWarningLimit: 300, // Предупреждать о чанках > 300kB
    
    rollupOptions: {
      output: {
        // 🚀 КРИТИЧНО: Split vendor chunks для кэширования и экономии трафика
        manualChunks: {
          // React core - кэшируется надолго
          'react-core': ['react', 'react-dom'],
          // Chart.js - большая библиотека, отдельный чанк
          'charts': ['chart.js', 'react-chartjs-2'],
          // Telegram SDK - специфичный для платформы
          'telegram': ['@telegram-apps/sdk-react', '@telegram-apps/signals', '@telegram-apps/transformers'],
          // i18n - загружается только если нужны переводы
          'i18n': ['i18next', 'react-i18next'],
          // Router - загружается при навигации
          'router': ['react-router-dom'],
          // State management
          'state': ['zustand']
        },
        // Оптимизированные имена файлов для кэширования
        chunkFileNames: 'js/[name]-[hash].js',
        entryFileNames: 'js/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]'
      }
    }
  },
  
  // 🚀 КРИТИЧНО: Оптимизация зависимостей для быстрой загрузки
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      '@telegram-apps/sdk-react',
      'react-router-dom',
      'zustand',
      'i18next',
      'react-i18next'
    ],
    // Exclude heavy dependencies that should be code-split
    exclude: ['chart.js', 'react-chartjs-2']
  },
}})