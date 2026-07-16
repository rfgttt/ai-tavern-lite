/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Background layers - deep brown-black, purple-black, ink-blue-black
        tavern: {
          bg: {
            deepest: '#0d0a0f',
            primary: '#141018',
            secondary: '#1a1520',
            tertiary: '#221b2a',
            elevated: '#2a2235',
          },
          // Amber gold, warm orange - primary accent
          gold: {
            50: '#fdf8ed',
            100: '#faefd4',
            200: '#f5dda8',
            300: '#eec471',
            400: '#e6a94a',
            500: '#d98f2e',
            600: '#c47424',
            700: '#a3591f',
            800: '#854720',
            900: '#6d3b1e',
          },
          // Gray-purple - secondary accent
          mist: {
            50: '#f6f4f9',
            100: '#ebe5f2',
            200: '#d5cbe4',
            300: '#b8a6cf',
            400: '#9a83b8',
            500: '#7f66a0',
            600: '#6a5086',
            700: '#57416c',
            800: '#473658',
            900: '#3c2e4a',
          },
          // Rose red - tertiary accent
          rose: {
            400: '#d47a8a',
            500: '#b85c6e',
            600: '#9a4657',
          },
          // Text colors - parchment tones
          text: {
            primary: '#f0e8d8',
            secondary: '#b8ad9a',
            muted: '#7d7365',
            inverse: '#1a1520',
          },
          // Border colors
          border: {
            subtle: '#2a2235',
            default: '#3a3045',
            strong: '#4a4055',
            gold: 'rgba(230, 169, 74, 0.3)',
          },
          // Glass backdrop colors
          glass: {
            light: 'rgba(42, 34, 53, 0.6)',
            medium: 'rgba(26, 21, 32, 0.75)',
            dark: 'rgba(13, 10, 15, 0.85)',
          },
          // Parchment - for message bubbles
          parchment: {
            dark: 'rgba(34, 27, 42, 0.7)',
            light: 'rgba(42, 34, 53, 0.5)',
          },
        },
      },
      fontFamily: {
        sans: [
          'system-ui',
          'Microsoft YaHei',
          'PingFang SC',
          'Noto Sans SC',
          'sans-serif',
        ],
        serif: [
          '"Noto Serif SC"',
          '"Source Han Serif SC"',
          'Georgia',
          'serif',
        ],
      },
      borderRadius: {
        'sm': '6px',
        'md': '10px',
        'lg': '14px',
        'xl': '18px',
        '2xl': '24px',
        'full': '9999px',
      },
      boxShadow: {
        'soft': '0 2px 8px rgba(0, 0, 0, 0.2)',
        'medium': '0 4px 16px rgba(0, 0, 0, 0.3)',
        'large': '0 8px 32px rgba(0, 0, 0, 0.4)',
        'glow-gold': '0 0 20px rgba(230, 169, 74, 0.15)',
        'glow-gold-strong': '0 0 30px rgba(230, 169, 74, 0.25)',
        'inner-soft': 'inset 0 1px 0 rgba(255, 255, 255, 0.03)',
      },
      backdropBlur: {
        'xs': '2px',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-in-left': 'slideInLeft 0.3s ease-out',
        'slide-in-right': 'slideInRight 0.3s ease-out',
        'breath': 'breath 4s ease-in-out infinite',
        'pulse-dot': 'pulseDot 1.4s ease-in-out infinite',
        'float': 'float 6s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideInLeft: {
          '0%': { opacity: '0', transform: 'translateX(-20px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        slideInRight: {
          '0%': { opacity: '0', transform: 'translateX(20px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        breath: {
          '0%, 100%': { opacity: '0.4', boxShadow: '0 0 8px rgba(230, 169, 74, 0.2)' },
          '50%': { opacity: '0.7', boxShadow: '0 0 16px rgba(230, 169, 74, 0.4)' },
        },
        pulseDot: {
          '0%, 80%, 100%': { opacity: '0.3', transform: 'scale(0.8)' },
          '40%': { opacity: '1', transform: 'scale(1)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-6px)' },
        },
      },
      transitionTimingFunction: {
        'tavern': 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
    },
  },
  plugins: [],
}
