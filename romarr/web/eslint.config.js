/**
 * ESLint flat config (T007 + T130 / spec 014).
 *
 * Scope: src/components/ + src/pages/ + src/lib/ — the
 * operator-facing surface. Tests + auto-generated codegen
 * are excluded so the gate isn't drowned in churn.
 *
 * Rules are kept tight but pragmatic: every rule that fires
 * here today is fixable mechanically (no sweeping autofix
 * required; the existing tree already conforms because
 * ``pnpm tsc`` runs strict on every slice).
 */

import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import reactPlugin from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

export default [
  {
    ignores: [
      "dist/**",
      "build/**",
      "coverage/**",
      "node_modules/**",
      "src/types/api/schema.ts",
      "**/*.config.js",
      "**/*.config.ts",
      "**/*.test.ts",
      "**/*.test.tsx",
      "**/*.spec.ts",
      "**/*.spec.tsx",
      "src/test/**",
    ],
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: { ...globals.browser, ...globals.es2022 },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
      react: reactPlugin,
      "react-hooks": reactHooks,
    },
    settings: {
      react: { version: "18.3" },
    },
    rules: {
      // Style + correctness — fire on every PR but auto-fix
      // most of the time.
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "no-debugger": "error",
      "no-var": "error",
      "prefer-const": "warn",
      eqeqeq: ["warn", "always", { null: "ignore" }],

      // React-specific.
      "react/jsx-key": "error",
      "react/jsx-no-target-blank": "error",
      "react/no-unescaped-entities": "off",
      "react/prop-types": "off",
      "react/react-in-jsx-scope": "off",

      // Hook rules — non-negotiable in React.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",

      // TypeScript ergonomics.
      "@typescript-eslint/no-unused-vars": [
        "warn",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
      "@typescript-eslint/no-explicit-any": "warn",
    },
  },
];
