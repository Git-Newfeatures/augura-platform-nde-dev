import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  // Build output is the only non-app folder under apps/web.
  globalIgnores(['dist']),

  // App source — runs in the browser.
  {
    files: ['src/**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      // argsIgnorePattern ^[A-Z_] mirrors varsIgnorePattern: a capitalized binding is a
      // component/constant (e.g. a destructured `[Icon,…]` rendered as <Icon/>), which the
      // base rule can't see as used in JSX without eslint-plugin-react's jsx-uses-vars.
      'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]', argsIgnorePattern: '^[A-Z_]' }],
      // react-compiler-era rules (eslint-plugin-react-hooks v6) flag working patterns
      // on this pre-compiler codebase. Kept visible as warnings (tech-debt backlog)
      // rather than blocking. The correctness rules (rules-of-hooks, no-undef) stay errors.
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/static-components': 'warn',
      'react-hooks/immutability': 'warn',
      // Debug logging must not ship; warn/error are intentional diagnostics.
      'no-console': ['warn', { allow: ['warn', 'error'] }],
    },
  },

  // Root config files run under Node (vite.config.js, eslint.config.js).
  {
    files: ['*.js'],
    extends: [js.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.node,
      parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
    },
    rules: {
      'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]', argsIgnorePattern: '^_' }],
    },
  },

  // shadcn/ui primitives re-export helpers alongside components by design.
  {
    files: ['src/components/ui/**/*.{js,jsx}'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
])
