const { fontFamily } = require("tailwindcss/defaultTheme")
// tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
    // content: ["./templates/*.html", "./components/**/*.{js,ts,jsx,tsx}"],
    content: [
        "./templates/**/*.{ts,tsx,html,js}",
        "./components/**/*.{ts,tsx,html,js}"
    ],
    theme: {
        container: {
            center: true,
            padding: "2rem",
            screens: {
                "2xl": "1400px",
            },
        },
        extend: {
            keyframes: {
                "accordion-down": {
                    from: { height: "0" },
                    to: { height: "var(--radix-accordion-content-height)" },
                },
                "accordion-up": {
                    from: { height: "var(--radix-accordion-content-height)" },
                    to: { height: "0" },
                },
            },
            animation: {
                "accordion-down": "accordion-down 0.2s ease-out",
                "accordion-up": "accordion-up 0.2s ease-out",
            },
            colors: {
                border: "hsl(var(--border))",
                input: "hsl(var(--input))",
                ring: "hsl(var(--ring))",
                background: "hsl(var(--background))",
                foreground: "hsl(var(--foreground))",
                primary: {
                    DEFAULT: "hsl(var(--primary))",
                    foreground: "hsl(var(--primary-foreground))",
                },
                secondary: {
                    DEFAULT: "hsl(var(--secondary))",
                    foreground: "hsl(var(--secondary-foreground))",
                },
                destructive: {
                    DEFAULT: "hsl(var(--destructive))",
                    foreground: "hsl(var(--destructive-foreground))",
                },
                muted: {
                    DEFAULT: "hsl(var(--muted))",
                    foreground: "hsl(var(--muted-foreground))",
                },
                accent: {
                    DEFAULT: "hsl(var(--accent))",
                    foreground: "hsl(var(--accent-foreground))",
                },
                popover: {
                    DEFAULT: "hsl(var(--popover))",
                    foreground: "hsl(var(--popover-foreground))",
                },
                card: {
                    DEFAULT: "hsl(var(--card))",
                    foreground: "hsl(var(--card-foreground))",
                },
                success: {
                    DEFAULT: "hsl(var(--success))",
                    foreground: "hsl(var(--success-foreground))",
                },
                warning: {
                    DEFAULT: "hsl(var(--warning))",
                    foreground: "hsl(var(--warning-foreground))",
                },
                // El menu lateral de shadcn usa su propia familia de tokens
                // (`bg-sidebar`, `hover:bg-sidebar-accent`, ...). Sin declararla
                // aqui, Tailwind no emite ni una de esas clases y el menu se
                // queda transparente en cuanto se superpone al contenido.
                sidebar: {
                    DEFAULT: "hsl(var(--sidebar))",
                    foreground: "hsl(var(--sidebar-foreground))",
                    primary: {
                        DEFAULT: "hsl(var(--sidebar-primary))",
                        foreground: "hsl(var(--sidebar-primary-foreground))",
                    },
                    accent: {
                        DEFAULT: "hsl(var(--sidebar-accent))",
                        foreground: "hsl(var(--sidebar-accent-foreground))",
                    },
                    border: "hsl(var(--sidebar-border))",
                    ring: "hsl(var(--sidebar-ring))",
                },
                // Tokens de marca CER, para usos puntuales fuera del sistema shadcn.
                cer: {
                    blue: "hsl(var(--cer-blue))",
                    cyan: "hsl(var(--cer-cyan))",
                    soft: "hsl(var(--cer-soft))",
                },
            },
            borderRadius: {
                lg: `var(--radius)`,
                md: `calc(var(--radius) - 2px)`,
                sm: "calc(var(--radius) - 4px)",
            },
            // `var(--font-sans)` no la definia nadie, asi que la tipografia
            // efectiva siempre fue la pila de reserva de Tailwind. Queda
            // explicita en vez de depender de una variable inexistente
            // (AUD-FE-025).
            fontFamily: {
                sans: [...fontFamily.sans],
            },
            keyframes: {
                "accordion-down": {
                    from: { height: "0" },
                    to: { height: "var(--radix-accordion-content-height)" },
                },
                "accordion-up": {
                    from: { height: "var(--radix-accordion-content-height)" },
                    to: { height: "0" },
                },
            },
            animation: {
                "accordion-down": "accordion-down 0.2s ease-out",
                "accordion-up": "accordion-up 0.2s ease-out",
            },
        },
    },
    plugins: [require("tailwindcss-animate")],
};