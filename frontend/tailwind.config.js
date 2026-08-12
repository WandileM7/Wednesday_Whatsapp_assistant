/** @type {import('tailwindcss').Config} */
// Tokens for the "Wednesday OS Glass" aurora system. The material itself
// (blur, specular edges, grain, motion) lives in index.css — these are just the
// flat values components reference.
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        void: '#06040d',
        // The one accent ramp. 400 is the colour you actually see in the UI;
        // 500/600 are for fills and glows, where the darker violet reads better.
        iris: {
          300: '#d6c2ff',
          400: '#c4a4ff',
          500: '#a855f7',
          600: '#7c3aed',
          700: '#5b21b6',
          900: '#3b0f80',
        },
        // Text ramp, lightest to faintest. Anything at `faint` or below is
        // decoration — it does not clear AA for body copy over the aurora.
        ink:   '#f4f1ff',
        soft:  '#e6e1f7',
        body:  '#d5cfe8',
        lav:   '#cfc8e6',
        muted: '#a79ec4',
        dim:   '#9c94ba',
        faint: '#7a7396',
        // Warn/error. The accent ramp is violet end to end, so problems need a
        // hue that cannot be mistaken for "normal but emphasised".
        alert: {
          400: '#fbbf24',
          500: '#fb7185',
        },
        // Retained so the orb/gesture code that predates this theme still builds.
        surface: {
          void: '#0a0812',
          base: '#100c1a',
          low:  '#171223',
          mid:  '#1c1730',
          high: '#28213f',
        },
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'SF Pro Display', 'Inter',
               'Helvetica Neue', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontWeight: {
        // The design leans on 450 — a real weight in variable Inter/SF, and the
        // reason its secondary text reads lighter than a normal 400.
        book: '450',
      },
      borderRadius: {
        card:  '20px',
        panel: '26px',
        hero:  '32px',
      },
      transitionTimingFunction: {
        stage: 'cubic-bezier(.6,0,.2,1)',
      },
    },
  },
  plugins: [],
}
