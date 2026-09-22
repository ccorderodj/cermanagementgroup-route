import { createRoot } from 'react-dom/client';
import {
    StoreProvider,
    UserProvider,
    AppProvider,
} from '@/app/providers/StoreProvider';
import { Toaster, TooltipProvider } from '@/shared/ui/shadcn/new-york';
import App from './app/App';
import '@/shared/config/i18n/i18n';
import './style.scss';

/**
 * Punto de entrada del bundle.
 *
 * Se retiro `ThemeProvider` y la hoja `app/styles/index.scss` (D12,
 * AUD-FE-006, AUD-FE-009): el modo oscuro no forma parte del producto, el
 * toggle no llegaba a afectar a las utilidades `dark:` de Tailwind —que no
 * tenia configurado `darkMode`— y aquel SCSS traia un sistema de temas
 * completo de otro proyecto (`normal`, `dark`, `orange`) que competia con los
 * tokens CER por el estilo de `body`.
 *
 * Queda un solo sistema de color: `style.scss` + `tailwind.config.js`.
 */

const container = document.getElementById('rootReact');

if (container) {
    const root = createRoot(container);
    root.render(
        <AppProvider>
            <UserProvider>
                <StoreProvider>
                    <TooltipProvider delayDuration={0}>
                        <App />
                        <Toaster />
                    </TooltipProvider>
                </StoreProvider>
            </UserProvider>
        </AppProvider>,
    );
}
