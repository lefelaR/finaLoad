import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#e7eef4",
        muted: "#8ea3b5",
        panel: "#10202c",
        line: "#1d3548",
        bull: "#3ddc97",
        bear: "#ff5d73",
        amber: "#f0b429",
        sea: "#7eb6ff",
      },
      fontFamily: {
        sans: ["Outfit", "system-ui", "sans-serif"],
        display: ["Fraunces", "Georgia", "serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
