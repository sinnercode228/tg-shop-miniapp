/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// GitHub Pages serves the demo from https://sinnercode228.github.io/tg-shop-miniapp/
const REPO_BASE = '/tg-shop-miniapp/';

export default defineConfig(({ command }) => ({
  base: process.env.VITE_BASE ?? (command === 'build' ? REPO_BASE : '/'),
  plugins: [react(), tailwindcss()],
  build: { chunkSizeWarningLimit: 600 },
  server: {
    port: 5173,
    fs: { allow: ['..'] },
    proxy: { '/api': 'http://localhost:8080' },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
}));
