/**
 * Configuración de ESLint.
 *
 * Dos criterios al ajustarla:
 *
 * 1. **Una regla que se incumple 41 veces por diseño no es una regla, es ruido.**
 *    `react/jsx-props-no-spreading` choca de frente con shadcn/ui, que es la
 *    librería de componentes elegida: sus primitivas reciben `{...props}`. Se
 *    apaga a propósito y queda dicho por qué.
 *
 * 2. `linebreak-style` ya no aparece: los finales de línea los normaliza
 *    `.gitattributes` con `* text=auto eol=lf`. Ese cambio bajó el lint de
 *    11.413 problemas a 145, de los que 11.268 eran CRLF (AUD-TOOL-003). El
 *    lint vuelve a ser una señal en lugar de un muro.
 */
module.exports = {
    ignorePatterns: [
        // Componentes de terceros (shadcn/ui). Su estilo es problema de upstream.
        'components/react/shared/ui/shadcn/',
        // Artefactos de build.
        'static/',
        'node_modules/',
    ],
    env: {
        browser: true,
        es2021: true,
    },
    extends: ['plugin:react/recommended', 'airbnb'],
    parser: '@typescript-eslint/parser',
    parserOptions: {
        ecmaFeatures: { jsx: true },
        ecmaVersion: 'latest',
        sourceType: 'module',
    },
    plugins: ['react', '@typescript-eslint', 'react-hooks', 'unused-imports'],
    rules: {
        // ── Formato ─────────────────────────────────────────────────────────
        indent: [2, 4],
        'react/jsx-indent': [2, 4],
        'react/jsx-indent-props': [2, 4],
        'max-len': ['error', { ignoreComments: true, ignoreStrings: true, code: 140 }],
        // Se rompe una expresión por línea con demasiada frecuencia en JSX con
        // texto intercalado; el resultado se lee peor, no mejor.
        'react/jsx-one-expression-per-line': 'off',
        'object-curly-newline': ['error', { consistent: true }],

        // ── Señal real ──────────────────────────────────────────────────────
        'unused-imports/no-unused-imports': 'error',
        'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
        'react-hooks/rules-of-hooks': 'error',
        'react-hooks/exhaustive-deps': 'error',
        // Un console.log olvidado imprime en la consola de quien usa la app.
        // `console.error` sí se permite: los errores hay que poder verlos.
        'no-console': ['error', { allow: ['error', 'warn'] }],
        'no-alert': 'error',

        // ── Incompatibles con el stack elegido ──────────────────────────────
        // shadcn/ui construye sus primitivas propagando props.
        'react/jsx-props-no-spreading': 'off',
        // TypeScript ya resuelve los imports.
        'import/no-unresolved': 'off',
        'import/extensions': 'off',
        'import/no-extraneous-dependencies': 'off',
        // La convención del proyecto es exportar con nombre desde los barriles.
        'import/prefer-default-export': 'off',
        'react/react-in-jsx-scope': 'off',
        'react/require-default-props': 'off',
        'react/function-component-definition': 'off',
        'react/jsx-filename-extension': [2, { extensions: ['.js', '.jsx', '.tsx'] }],
        'react/no-array-index-key': 'off',
        // Redux Toolkit usa Immer: mutar el borrador es el patrón correcto.
        'no-param-reassign': 'off',
        'no-shadow': 'off',
        'no-undef': 'off',
        'no-underscore-dangle': 'off',
        'arrow-body-style': 'off',
        'jsx-a11y/no-static-element-interactions': 'off',
        'jsx-a11y/click-events-have-key-events': 'off',
        // El preset trae `assert: 'both'`: exige que la etiqueta lleve
        // `htmlFor` **y además** envuelva al control. La accesibilidad pide
        // una de las dos, no las dos, y `htmlFor` es la que sirve cuando la
        // etiqueta no puede envolver al control — un buscador con su icono
        // posicionado encima, por ejemplo.
        //
        // Con `both` la regla prohibía el patrón correcto, así que en la
        // práctica se cumplía escribiendo `<span>` en vez de `<label>`: la
        // regla no mira los `span`, y ningún control quedaba nombrado. Pasaba
        // el lint y fallaba la pantalla.
        'jsx-a11y/label-has-associated-control': ['error', {
            assert: 'either',
            depth: 25,
        }],
    },
    globals: {
        __IS_DEV__: true,
        __API__: true,
        __PROJECT__: true,
    },
};
