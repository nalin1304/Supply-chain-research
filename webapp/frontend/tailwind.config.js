/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      colors: {
        cyber: {
          dark: '#09090b',
          panel: 'rgba(255, 255, 255, 0.03)',
          border: 'rgba(255, 255, 255, 0.08)',
          cyan: '#00f0ff',
          purple: '#b026ff',
          blue: '#1e3a8a',
        }
      },
      backgroundImage: {
        'cyber-grid': 'linear-gradient(to right, #1f2937 1px, transparent 1px), linear-gradient(to bottom, #1f2937 1px, transparent 1px)',
        'cyber-gradient': 'radial-gradient(circle at top right, rgba(176, 38, 255, 0.15), transparent 40%), radial-gradient(circle at bottom left, rgba(0, 240, 255, 0.15), transparent 40%)'
      }
    },
  },
  plugins: [],
}
