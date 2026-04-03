/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        wed: {
          50:  '#edfffe',
          100: '#c0fffc',
          200: '#81fef8',
          300: '#3afbf2',
          400: '#00e5dc',
          500: '#00c8c1',
          600: '#00a19e',
          cyan:   '#00d4ff',
          green:  '#34d399',
          red:    '#f87171',
          orange: '#fb923c',
          purple: '#a78bfa',
        },
        surface: {
          0:   '#060610',
          1:   '#0c0c1d',
          2:   '#12122a',
          3:   '#1a1a38',
          4:   '#222246',
        }
      },
      fontFamily: {
        display: ['Outfit', 'sans-serif'],
        body:    ['Inter', 'sans-serif'],
        mono:    ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.25rem',
      },
      animation: {
        'glow-pulse': 'glowPulse 3s ease-in-out infinite',
        'float':      'float 6s ease-in-out infinite',
        'slide-up':   'slideUp 0.5s ease-out',
        'fade-in':    'fadeIn 0.4s ease-out',
        'grid-scan':  'gridScan 8s linear infinite',
        'border-glow':'borderGlow 3s ease-in-out infinite',
        'ping-slow':  'ping 3s cubic-bezier(0, 0, 0.2, 1) infinite',
      },
      keyframes: {
        glowPulse: {
          '0%, 100%': { opacity: '0.4' },
          '50%':      { opacity: '1' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%':      { transform: 'translateY(-8px)' },
        },
        slideUp: {
          '0%':   { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        gridScan: {
          '0%':   { backgroundPosition: '0 0' },
          '100%': { backgroundPosition: '0 50px' },
        },
        borderGlow: {
          '0%, 100%': { borderColor: 'rgba(0, 212, 255, 0.15)' },
          '50%':      { borderColor: 'rgba(0, 212, 255, 0.4)' },
        },
      },
      backgroundImage: {
        'grid-pattern': `linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px),
                         linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px)`,
        'glow-radial':  'radial-gradient(ellipse at center, rgba(0, 212, 255, 0.08) 0%, transparent 70%)',
      },
      backgroundSize: {
        'grid': '50px 50px',
      },
    },
  },
  plugins: [],
}
