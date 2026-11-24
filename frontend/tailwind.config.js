/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        marca: {
          50: "#eef3fa",
          100: "#d6e2f2",
          600: "#2a4d7f",
          700: "#1f3a63",
          800: "#1b365d",
          900: "#13263f",
        },
      },
    },
  },
  plugins: [],
};
