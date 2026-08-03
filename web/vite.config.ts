import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 5173, // web_bridge owns 8080; dev server proxies game traffic to it
    proxy: {
      "/api": "http://127.0.0.1:8080",
      "/health": "http://127.0.0.1:8080",
      "/ws": { target: "ws://127.0.0.1:8080", ws: true },
    },
  },
  plugins: [
    react(),
    mode === 'development' &&
    componentTagger(),
  ].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "react-native": "react-native-web", // Add this line for web compatibility
    },
  },
  optimizeDeps: {
    exclude: ['react-native-game-engine'],
    esbuild: {
      jsxInject: "import React from 'react';",
      jsx: 'automatic'
    }
  }
}));
