import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  // Build output + non-app folders (reference designs, standalone sub-project,
  // backups, Python sim, data fixtures) are not part of the app and not linted.
  globalIgnores([
    'dist',
    'docs',
    'backup',
    'augura-corpus-intelligence',
    'simulation',
    'user-data',
    'validation_dataset_doc',
  ]),

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
    },
  },

  // Server-side: Vercel serverless functions, the shared agent runtime +
  // tools, Node build/utility scripts, and the test suites.
  {
    files: ['api/**/*.js', 'agents/**/*.js', 'tools/**/*.js', 'test/**/*.js', 'e2e/**/*.js', 'scripts/**/*.js', '*.js'],
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
