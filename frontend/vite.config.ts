import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served from https://<user>.github.io/NHL-SOG-Finder/ (a GitHub Pages
// project site), so asset URLs need that prefix. Pages paths are
// case-sensitive -- this must match the repo name's casing exactly, or
// every JS/CSS asset 404s and the page renders blank.
export default defineConfig({
  base: "/NHL-SOG-Finder/",
  plugins: [react()],
});
