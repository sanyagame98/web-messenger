import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef6ff",
          100: "#dceffe",
          200: "#b3deff",
          300: "#7fc4fe",
          400: "#46a4f7",
          500: "#1f86ec",
          600: "#1369cb",
          700: "#1255a2",
          800: "#134781",
          900: "#143c67",
        },
      },
    },
  },
  plugins: [],
};

export default config;
