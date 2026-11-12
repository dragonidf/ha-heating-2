import { defineConfig } from "vite";
/** Dedicated release build; never changes accepted synthetic bundle or its CI hashes. */
export default defineConfig({
  base: "./",
  build: {
    outDir: "dist-live",
    emptyOutDir: true,
    rollupOptions: {
      input: { livePanel: "src/live-panel.tsx" },
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name]-[hash].js",
      },
    },
  },
});
