import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
// SPA de una sola página: React + MapLibre. Tailwind v4 vía plugin de Vite.
export default defineConfig({
    plugins: [react(), tailwindcss()],
});
