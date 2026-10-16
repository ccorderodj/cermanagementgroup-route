import { ReactNode } from 'react';
import { Activity, MapPin, User } from 'lucide-react';

/**
 * Shell del supervisor de CER Route. **Solo móvil** (decisión D-03 de RTE01).
 *
 * No reutiliza `SidebarProvider`: un menú lateral de escritorio es justo lo que
 * esta experiencia no debe tener. Lo que hay es una barra inferior de tres
 * destinos, alcanzable con el pulgar, y el contenido ocupando el viewport
 * completo.
 *
 * La navegación son enlaces `<a>` normales, no un router de frontend: el patrón
 * de la casa es server-route + page-key, y meter aquí un router rompería la
 * mitad de la arquitectura (invariante 7).
 *
 * En pantallas anchas el contenido se centra en una columna estrecha en vez de
 * estirarse. No es una versión de escritorio —CER no pidió ninguna—: es que un
 * supervisor que abra esto en una tablet vea la misma interfaz y no una
 * deformada.
 */

type RouteMobileShellProps = {
    /** Título de la pantalla actual, en la cabecera compacta. */
    title: string;
    /** Clave de la pestaña activa de la barra inferior. */
    active: 'my-route' | 'activity' | 'me';
    children: ReactNode;
};

const TABS = [
    { key: 'my-route', label: 'My Route', href: '/route', icon: MapPin },
    { key: 'activity', label: 'Activity', href: '/route/activity', icon: Activity },
    { key: 'me', label: 'Me', href: '/route/me', icon: User },
] as const;

export function RouteMobileShell({ title, active, children }: RouteMobileShellProps) {
    return (
        <div className="flex min-h-svh flex-col bg-background">
            <header className="sticky top-0 z-10 border-b border-border bg-card">
                <div className="mx-auto w-full max-w-md px-4 py-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        CER Route
                    </p>
                    <h1 className="text-lg font-semibold text-foreground">{title}</h1>
                </div>
            </header>

            {/* `pb-24` deja sitio a la barra inferior fija: sin ello, el último
                bloque de contenido queda debajo de ella y no se puede leer. */}
            <main className="mx-auto w-full max-w-md flex-1 px-4 pb-24 pt-4">
                {children}
            </main>

            <nav
                className="fixed inset-x-0 bottom-0 border-t border-border bg-card"
                aria-label="Route sections"
            >
                <div className="mx-auto flex w-full max-w-md">
                    {TABS.map((tab) => {
                        const Icon = tab.icon;
                        const isActive = tab.key === active;

                        return (
                            <a
                                key={tab.key}
                                href={tab.href}
                                aria-current={isActive ? 'page' : undefined}
                                className={[
                                    // Objetivo táctil generoso: se usa de pie,
                                    // con una mano y a veces con guantes.
                                    'flex flex-1 flex-col items-center gap-1 py-3 text-xs font-medium',
                                    isActive
                                        ? 'text-primary'
                                        : 'text-muted-foreground',
                                ].join(' ')}
                            >
                                <Icon className="size-5" aria-hidden="true" />
                                {tab.label}
                            </a>
                        );
                    })}
                </div>
            </nav>
        </div>
    );
}
