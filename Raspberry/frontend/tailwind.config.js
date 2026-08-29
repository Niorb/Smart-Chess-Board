/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['"Outfit"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        nordic: {
          dark: '#0b0f17',
          surface: '#101726',
          card: '#141d2e',
          cardHover: '#1c2840',
          subtle: '#222f49',
          border: '#2a3a5c',
          borderLight: '#3e527d',
          birch: '#f5ecd7',
          birchDark: '#dfd1b5',
          walnut: '#8b5e3c',
          walnutDark: '#50331e',
          amber: '#f59e0b',
          amberGlow: '#fbbf24',
          emerald: '#10b981',
          cyan: '#06b6d4',
          rose: '#f43f5e',
          violet: '#8b5cf6',
          celadon: '#5eead4',
        },
      },
      boxShadow: {
        'artisan': '0 20px 40px -15px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 255, 255, 0.05)',
        'artisan-lg': '0 25px 50px -12px rgba(0, 0, 0, 0.85), 0 0 0 1px rgba(255, 255, 255, 0.08)',
        'amber-glow': '0 0 25px -5px rgba(245, 158, 11, 0.45)',
        'emerald-glow': '0 0 25px -5px rgba(16, 185, 129, 0.45)',
        'cyan-glow': '0 0 25px -5px rgba(6, 182, 212, 0.45)',
        'rose-glow': '0 0 25px -5px rgba(244, 63, 94, 0.45)',
      },
      animation: {
        'pulse-subtle': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'ripple': 'ripple 2s cubic-bezier(0, 0.2, 0.8, 1) infinite',
        'flux': 'flux 4s ease-in-out infinite alternate',
      },
      keyframes: {
        ripple: {
          '0%': { transform: 'scale(0.8)', opacity: '1' },
          '100%': { transform: 'scale(2.2)', opacity: '0' },
        },
        flux: {
          '0%': { filter: 'hue-rotate(0deg) brightness(1)' },
          '100%': { filter: 'hue-rotate(30deg) brightness(1.15)' },
        },
      },
    },
  },
  plugins: [],
}
