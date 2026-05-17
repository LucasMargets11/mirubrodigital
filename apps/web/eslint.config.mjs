// @ts-check
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import nextConfig from 'eslint-config-next/core-web-vitals';

export default [
  // ESLint built-in recommended rules (no-debugger, no-undef, etc.)
  js.configs.recommended,

  // Next.js flat config: React, React Hooks, @next/next, jsx-a11y, import,
  // TypeScript parser + plugin, and core-web-vitals rules.
  ...nextConfig,

  // TypeScript-ESLint recommended rules on top of the parser already set
  // by eslint-config-next.
  ...tseslint.configs.recommended,

  // Custom rule overrides — restores original severity levels.
  {
    files: ['**/*.ts', '**/*.tsx'],
    rules: {
      // Disable base rule; TS-aware replacement is below.
      'no-unused-vars': 'off',

      // Was `warn` in @typescript-eslint/recommended ≤v6; elevated to `error`
      // in v7+. Keep as warn to match the pre-migration behaviour.
      '@typescript-eslint/no-explicit-any': 'warn',
      // New rules in typescript-eslint v8 — surface as warnings.
      '@typescript-eslint/no-unsafe-function-type': 'warn',
      '@typescript-eslint/no-require-imports': 'warn',

      // Custom project rule.
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],

      // New rules added in react-hooks v7 that were not in the original
      // plugin:react-hooks/recommended (v4). Surface as warnings so the
      // team can address them incrementally.
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/set-state-in-render': 'warn',
      'react-hooks/preserve-manual-memoization': 'warn',
      'react-hooks/static-components': 'warn',
      'react-hooks/purity': 'warn',

      // exhaustive-deps was `warn` in original react-hooks/recommended.
      'react-hooks/exhaustive-deps': 'warn',
    },
  },

  // Global ignores
  {
    ignores: [
      'node_modules/**',
      '.next/**',
      'dist/**',
      'build/**',
      'coverage/**',
      'next-env.d.ts',
      // Root-level CommonJS/JS config files use Node globals that are out of
      // scope for source linting (next lint never checked these either).
      'postcss.config.js',
      'prettier.config.cjs',
      'tailwind.config.ts',
      'vitest.config.ts',
      'vitest.setup.ts',
      'next.config.mjs',
    ],
  },
];
