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
        premium: {
          background: '#050505', // Pitch black
          panel: '#111111', // Very dark gray for panels
          border: '#27272a', // Subtle gray border
          accent: '#6366f1', // Elegant Indigo
          accentHover: '#4f46e5',
          text: '#fafafa', // High contrast white
          textMuted: '#a1a1aa', // Muted text
        }
      },
      backgroundImage: {
        'premium-gradient': 'radial-gradient(circle at top, rgba(99, 102, 241, 0.05), transparent 50%)',
        'subtle-grid': 'linear-gradient(to right, #18181b 1px, transparent 1px), linear-gradient(to bottom, #18181b 1px, transparent 1px)'
      }
    },
  },
  plugins: [],
}
