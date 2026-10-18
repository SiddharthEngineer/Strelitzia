/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Built into the Python package, so `strelitzia serve` (and pip installs) need no Node.
// `base` is the dashboard's URL prefix; keep it in step with PREFIX in src/strelitzia/web/paths.py.
const base = '/strelitzia/dashboard/';

export default defineConfig({
  base,
  plugins: [react()],
  build: {
    outDir: '../src/strelitzia/web/static',
    emptyOutDir: true,
  },
  server: {
    proxy: { [`${base}api`]: 'http://127.0.0.1:8765' },
  },
  test: {
    environment: 'jsdom',
    // Vitest serves from '/' and sets BASE_URL to match; pin it so the tests see the real prefix.
    env: { BASE_URL: base },
    setupFiles: ['./src/test-setup.ts'],
    // Process styles.css so the theme tests can read it (`?raw`); vitest stubs CSS out by default.
    css: { include: [/styles\.css/] },
  },
});
