// Copyright (C) 2026 William Johnason / axoviq.com
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: "/app/",
  build: {
    outDir: "dist",
  },
})
