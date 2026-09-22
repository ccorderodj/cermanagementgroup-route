import {
    memo, Suspense, useEffect, useState,
} from 'react';
import { RootComponents } from '../config/mainContentConfig';
import { PageLoader } from '@/widgets/PageLoader';
import {
    SidebarInset,
    SidebarProvider,
} from '@/shared/ui/shadcn/new-york';
import CookieService from '@/shared/lib/utils/CookieService';
import { AppSidebar } from './AppSidebar';
import { ComponentRoot } from './maincontent';
import { AppTopbar } from '@/widgets/Layout';

/**
 * Resolución de la página a partir de la clave que imprime el servidor.
 *
 * El servidor decide qué página es (`name=` de la ruta FastAPI -> `url_name` ->
 * `data-current-page`) y aquí solo se busca el componente correspondiente. No
 * hay router de frontend, y no debe haberlo: el patrón es server-route + page-key.
 *
 * Los tres modos de fallo posibles se tratan de forma distinta y **visible**.
 * Antes, dos de los tres eran silenciosos: el árbol se quedaba en `null` sin
 * que nada indicara por qué, que es justo lo que hace tan difícil de
 * diagnosticar un desajuste de page-key (AUD-FE-015).
 */

const pagesWithoutLayout: ComponentRoot[] = [
    // Sin sesión no hay shell: quien todavía no entró no ve la barra lateral
    // ni la superior. Una aplicación que publique páginas anónimas las añade.
    ComponentRoot.LOGIN,
    ComponentRoot.PASSWORDRESET,
    ComponentRoot.CHANGEPASSWORD,
];

type Resolution =
    | { status: 'pending' }
    | { status: 'ready'; page: string }
    | { status: 'error'; reason: string };

const MISSING_ANCHOR = 'The page did not render because the server template has no '
    + '<div id="rc-currentPage"> element.';

const EMPTY_KEY = 'The page did not render because data-current-page is empty: the FastAPI '
    + 'route is missing its name= attribute.';

function unknownKey(key: string): string {
    return `The page did not render because "${key}" has no entry in RootComponents. `
        + 'The FastAPI route name, the ComponentRoot enum and the RootComponents map '
        + 'must all use exactly the same string.';
}

const AppMainContent = () => {
    const [resolution, setResolution] = useState<Resolution>({ status: 'pending' });
    const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(false);

    useEffect(() => {
        const sidebarState = CookieService.getCookie('sidebar:state');

        if (sidebarState === null || sidebarState === undefined) {
            // Primera visita: el menú se abre.
            setIsSidebarOpen(true);
            CookieService.setCookie('sidebar:state', 'true', 30);
        } else {
            setIsSidebarOpen(sidebarState === 'true');
        }
    }, []);

    useEffect(() => {
        const anchor = document.getElementById('rc-currentPage');

        if (!anchor) {
            setResolution({ status: 'error', reason: MISSING_ANCHOR });
            return;
        }

        const key = anchor.getAttribute('data-current-page');

        if (!key) {
            setResolution({ status: 'error', reason: EMPTY_KEY });
            return;
        }

        if (!RootComponents[key]) {
            setResolution({ status: 'error', reason: unknownKey(key) });
            return;
        }

        setResolution({ status: 'ready', page: key });
    }, []);

    if (resolution.status === 'pending') {
        return <PageLoader />;
    }

    if (resolution.status === 'error') {
        // El diagnóstico va a la consola siempre; en desarrollo además se pinta,
        // porque una pantalla en blanco no dice nada a quien acaba de añadir
        // una página. En producción no se enseña al usuario un problema de
        // cableado que no puede resolver.
        // eslint-disable-next-line no-console
        console.error(`[page-key] ${resolution.reason}`);

        if (!__IS_DEV__) {
            return null;
        }

        return (
            <div className="m-6 rounded-lg border border-destructive/40 bg-destructive/5 p-6">
                <p className="font-semibold text-destructive">Page could not be rendered</p>
                <p className="mt-2 text-sm text-muted-foreground">{resolution.reason}</p>
            </div>
        );
    }

    const { page } = resolution;

    // Sin `Portal`: el que había buscaba un elemento cuyo id era la clave de
    // página, nunca lo encontraba y caía siempre en `document.body`, dejando
    // vacío el `#rootReact` de la plantilla (AUD-FE-016).
    return (
        <Suspense fallback={<PageLoader />}>
            {pagesWithoutLayout.includes(page as ComponentRoot) ? (
                RootComponents[page]
            ) : (
                <div className="flex min-h-svh bg-background">
                    <SidebarProvider defaultOpen={isSidebarOpen}>
                        <AppSidebar />
                        {/* `min-w-0` no es cosmetico: `SidebarInset` es un
                            elemento flexible y su `min-width: auto` vale su
                            contenido minimo, asi que cualquier bloque ancho
                            —una tabla, una tira de pestanas— ensancha TODA la
                            maquetacion en vez de desplazarse dentro de su
                            propio contenedor. En un movil eso se traduce en
                            scroll horizontal de la pagina entera, que es justo
                            lo que el requisito prohibe. */}
                        <SidebarInset className="min-w-0 bg-background">
                            <AppTopbar />
                            <section id="main-content" className="min-h-[calc(100svh-4rem)]">
                                {RootComponents[page]}
                            </section>
                        </SidebarInset>
                    </SidebarProvider>
                </div>
            )}
        </Suspense>
    );
};

export default memo(AppMainContent);
