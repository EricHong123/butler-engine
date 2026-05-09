/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  safelist: [
    { pattern: /^(bg|text|border)-(surface|card|muted|gold)/ },
    'bg-gray-800', 'bg-gray-900', 'bg-gray-800/50', 'bg-gray-800/30',
    'bg-black/30', 'bg-black/50', 'bg-blue-500/10', 'bg-blue-500/20',
    'bg-green-500/10', 'bg-green-500/20', 'bg-red-500/10', 'bg-red-500/20',
    'bg-yellow-500/10', 'bg-yellow-500/20',
    'text-white', 'text-gray-200', 'text-gray-300', 'text-gray-400', 'text-gray-700',
    'text-green-400', 'text-red-400', 'text-blue-400', 'text-yellow-400',
    'border-gray-700', 'border-gray-700/50', 'border-gray-800', 'border-gray-800/30', 'border-gray-800/50',
    'rounded-lg', 'rounded-xl', 'rounded-2xl', 'rounded-full',
    'animate-spin', 'animate-pulse',
    'line-clamp-2',
  ],
  theme: {
    extend: {
      colors: {
        gold: { 400: '#E8C86A', 500: '#D4A83C', 600: '#B8922E' },
        card: '#181C22',
        surface: '#0E1014',
        muted: '#707070',
      },
    },
  },
  plugins: [],
};
