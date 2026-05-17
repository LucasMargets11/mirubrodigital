/**
 * @deprecated Legacy eslintrc format — no longer works with ESLint 9 flat config.
 * Migrate to base.mjs and create an eslint.config.mjs in your app.
 * See packages/config/eslint/base.mjs for the flat-config factory.
 */
module.exports = {
  root: false,
  env: {
    browser: true,
    es2021: true,
  },
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "next",
    "next/core-web-vitals",
  ],
  parser: "@typescript-eslint/parser",
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
  },
  plugins: ["@typescript-eslint"],
  ignorePatterns: ["node_modules/", ".next/", "dist/"],
  rules: {
    "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
  },
};
