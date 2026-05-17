/**
 * Shared ESLint flat-config factory for Next.js / TypeScript apps.
 *
 * Each consuming app must install these devDependencies:
 *   eslint  @eslint/js  typescript-eslint  eslint-config-next
 *
 * Usage in apps/web/eslint.config.mjs (or any app's eslint.config.mjs):
 *
 *   import js        from '@eslint/js';
 *   import tseslint  from 'typescript-eslint';
 *   import nextConfig from 'eslint-config-next/core-web-vitals';
 *   import { createConfig } from '../../packages/config/eslint/base.mjs';
 *
 *   export default createConfig({ js, tseslint, nextConfig });
 *
 * The factory pattern is required because Node.js resolves bare imports
 * relative to the file they appear in, so the consuming app must supply
 * its own copies of the shared dependencies.
 */

/**
 * @param {{ js: import('@eslint/js'), tseslint: import('typescript-eslint'), nextConfig: unknown[] }} deps
 * @returns {unknown[]}
 */
export function createConfig({ js, tseslint, nextConfig }) {
  return [
    // ESLint built-in recommended rules (no-debugger, no-undef, etc.)
    js.configs.recommended,

    // Next.js flat config: React, React Hooks, @next/next, jsx-a11y, import,
    // TypeScript parser + plugin, and core-web-vitals rules.
    ...nextConfig,

    // TypeScript-ESLint recommended rules on top of the parser already set
    // by eslint-config-next (no-explicit-any, etc.)
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
        // plugin:react-hooks/recommended (v4). Surface as warnings.
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
      ],
    },
  ];
}
