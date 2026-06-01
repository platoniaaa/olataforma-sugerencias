import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Paper: fondo crema "papel tecnico" en vez de blanco frio.
        paper: {
          DEFAULT: "#fafaf7",
          50: "#fdfdfb",
          100: "#f6f5ee",
          200: "#ebe9dd",
        },
        // Ink: tinta calida, mejor lectura prolongada que slate puro.
        ink: {
          DEFAULT: "#1c1917",
          50: "#fafaf9",
          100: "#f5f5f4",
          200: "#e7e5e4",
          300: "#d6d3d1",
          400: "#a8a29e",
          500: "#78716c",
          600: "#57534e",
          700: "#44403c",
          800: "#292524",
          900: "#1c1917",
        },
        // Brand: azul Curifor (identidad — no se toca).
        brand: {
          DEFAULT: "#1e40af",
          50: "#eff4ff",
          100: "#dbe6fe",
          200: "#bfd3fc",
          600: "#1e40af",
          700: "#1b3a9c",
          800: "#1a3486",
          900: "#172e75",
        },
        // Accent: clay/amber industrial para resaltes y acciones secundarias.
        accent: {
          DEFAULT: "#c2410c",
          50: "#fff7ed",
          100: "#ffedd5",
          500: "#f97316",
          600: "#ea580c",
          700: "#c2410c",
          800: "#9a3412",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "Georgia", "serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      letterSpacing: {
        tightest: "-0.04em",
      },
      boxShadow: {
        // Sombras suaves y calidas en vez de las default azuladas.
        card: "0 1px 0 rgba(28,25,23,0.04), 0 1px 2px rgba(28,25,23,0.04)",
        lift: "0 2px 8px rgba(28,25,23,0.06), 0 1px 2px rgba(28,25,23,0.04)",
      },
    },
  },
  plugins: [],
};

export default config;
