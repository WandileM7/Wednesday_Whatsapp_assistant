/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        jarvis: {
          blue: '#00d4ff',
          'blue-dim': 'rgba(0, 212, 255, 0.3)',
          gold: '#ffd700',
          red: '#ff3b3b',
          green: '#00ff88',
          orange: '#ff9500',
          dark: '#0a0a12',
          panel: 'rgba(10, 15, 30, 0.85)',
        }
      },
      fontFamily: {
        orbitron: ['Orbitron', 'sans-serif'],
        rajdhani: ['Rajdhani', 'sans-serif'],
        mono: ['Share Tech Mono', 'monospace'],
      },
      animation: {
        'pulse-glow': 'pulseGlow 3s ease-in-out infinite',
        'spin-slow': 'spin 10s linear infinite',
        'spin-slower': 'spin 15s linear infinite reverse',
        'reactor-pulse': 'reactorPulse 3s ease-in-out infinite',
        'grid-pulse': 'gridPulse 4s ease-in-out infinite',
      },
      keyframes: {
        pulseGlow: {
          '0%, 100%': { filter: 'brightness(1)' },
          '50%': { filter: 'brightness(1.2)' },
        },
        reactorPulse: {
          '0%, 100%': { boxShadow: '0 0 60px #00d4ff, 0 0 100px rgba(0, 212, 255, 0.5)' },
          '50%': { boxShadow: '0 0 80px #00d4ff, 0 0 140px rgba(0, 212, 255, 0.7)' },
        },
        gridPulse: {
          '0%, 100%': { opacity: '0.5' },
          '50%': { opacity: '1' },
        }
      }
    },
  },
  plugins: [],
}
