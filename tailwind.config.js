/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./inventory/**/*.html",
    "./inventory/**/*.py", // optional if using template tags in views
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
