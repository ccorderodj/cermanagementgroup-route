import axios, { AxiosError, AxiosHeaders } from 'axios';

/**
 * Cliente HTTP de la aplicación. **El único** (D13).
 *
 * Antes convivían dos: este Axios y un `rtkApi` de RTK Query montado en el
 * store con cero endpoints definidos. Redux Toolkit se mantiene para estado y
 * thunks, pero las llamadas salen todas por aquí.
 *
 * Tres cosas que centraliza y que antes estaban repartidas o no existían:
 *
 * 1. **CSRF.** La sesión viaja en cookie, así que el navegador la adjunta sola
 *    a cualquier petición hacia este origen. El servidor emite `cer_csrf_token`
 *    —legible por JS a propósito— y aquí se copia a la cabecera `X-CSRF-Token`
 *    en todo método que muta estado. El backend rechaza la petición si no
 *    coinciden. Antes se enviaba `X-CSRFToken: window.csrfToken`, variable que
 *    no se asignaba en ninguna parte: la cabecera iba siempre vacía y el
 *    backend no comprobaba nada.
 *
 * 2. **Normalización de errores.** Un fallo de API llega a los thunks con la
 *    misma forma venga de donde venga.
 *
 * 3. **Sesión caducada.** Un 401 lleva al login en vez de dejar la pantalla a
 *    medias.
 */

export const CSRF_COOKIE_NAME = 'cer_csrf_token';
export const CSRF_HEADER_NAME = 'X-CSRF-Token';

const MUTATING_METHODS = ['post', 'put', 'patch', 'delete'];

/** Lee una cookie por nombre. Devuelve `null` si no está. */
export function readCookie(name: string): string | null {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : null;
}

/** Forma uniforme de un error de API, ya legible para la interfaz. */
export interface ApiError {
    status: number | null;
    message: string;
    /** Errores por campo, cuando el backend devuelve validación de Pydantic. */
    fieldErrors?: Record<string, string>;
}

const GENERIC_MESSAGE = 'Something went wrong. Please try again.';

function extractFieldErrors(detail: unknown): Record<string, string> | undefined {
    if (!Array.isArray(detail)) return undefined;

    const fields: Record<string, string> = {};
    detail.forEach((item) => {
        if (!item || typeof item !== 'object') return;
        const { loc } = (item as { loc?: unknown[] });
        const { msg } = (item as { msg?: string });
        if (Array.isArray(loc) && typeof msg === 'string') {
            const field = String(loc[loc.length - 1]);
            fields[field] = msg;
        }
    });

    return Object.keys(fields).length ? fields : undefined;
}

export function normalizeApiError(error: unknown): ApiError {
    const axiosError = error as AxiosError<{ detail?: unknown }>;

    if (!axiosError?.isAxiosError) {
        return { status: null, message: GENERIC_MESSAGE };
    }

    const status = axiosError.response?.status ?? null;
    const detail = axiosError.response?.data?.detail;

    if (typeof detail === 'string') {
        return { status, message: detail };
    }

    const fieldErrors = extractFieldErrors(detail);
    if (fieldErrors) {
        return {
            status,
            message: 'Please review the highlighted fields.',
            fieldErrors,
        };
    }

    if (status === null) {
        return { status, message: 'The server is unreachable. Check your connection.' };
    }

    return { status, message: GENERIC_MESSAGE };
}

export const $api = axios.create({
    baseURL: '/api',
    // La sesión es una cookie: hay que enviarla.
    withCredentials: true,
});

$api.interceptors.request.use((config) => {
    const method = (config.method ?? 'get').toLowerCase();

    if (MUTATING_METHODS.includes(method)) {
        const token = readCookie(CSRF_COOKIE_NAME);
        if (token) {
            const headers = AxiosHeaders.from(config.headers);
            headers.set(CSRF_HEADER_NAME, token);
            config.headers = headers;
        }
    }

    return config;
});

$api.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
        // Sesión caducada o inválida: al login. La cookie ya viene limpia del
        // servidor, así que no hay estado que arrastrar — salvo la cola de
        // acciones pendientes en IndexedDB, que es independiente de la cookie
        // de sesión y sobrevive a este redirect (ver widgets/RouteOfflineQueue).
        //
        // `next` lleva de vuelta a donde estaba quien perdió la sesión, para
        // que reautenticarse no lo deje varado en el panel de Admin cuando
        // trabajaba, por ejemplo, en /route (D-09).
        if (error.response?.status === 401 && typeof window !== 'undefined') {
            const volver = encodeURIComponent(
                window.location.pathname + window.location.search,
            );
            window.location.assign(`/login?next=${volver}`);
        }

        return Promise.reject(error);
    },
);
