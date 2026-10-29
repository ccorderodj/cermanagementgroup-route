import { $api } from '@/shared/api';

/**
 * ¿Hay una versión nueva del frontend que esta pestaña no tiene?
 *
 * La página lleva su build en `<meta name="cer-build">`; cada respuesta de
 * `/static/` lleva el del servidor en `X-CER-Build` (ver `app/core/build.py`).
 * Una pestaña que vuelve a primer plano, que se restaura desde la caché de
 * ida y vuelta o que recupera la red los compara con un `HEAD` de `main.js`.
 *
 * Nunca recarga sola: avisa, y quien trabaja decide cuándo. No hay sondeo
 * periódico, y el `HEAD` es estático: no pasa por la sesión, así que no puede
 * mandar al login a nadie.
 */

const SONDA = '/static/javascript/main.js';
const CABECERA = 'x-cer-build';
/** Entre dos comprobaciones, como mínimo. Volver a la pestaña no es un evento raro. */
const INTERVALO_MINIMO_MS = 60_000;

let disponible = false;
let ultima = 0;
let enCurso = false;
const oyentes = new Set<() => void>();

export function buildDeEstaPagina(): string | null {
    return document.querySelector<HTMLMetaElement>('meta[name="cer-build"]')?.content || null;
}

export function hayActualizacion(): boolean {
    return disponible;
}

export function suscribirActualizacion(oyente: () => void): () => void {
    oyentes.add(oyente);
    return () => { oyentes.delete(oyente); };
}

/** También lo llama quien no pudo cargar un chunk: el build que lo tenía ya no está. */
export function avisarActualizacion(): void {
    if (disponible) return;
    disponible = true;
    oyentes.forEach((oyente) => oyente());
}

export async function comprobarActualizacion(ahora: number = Date.now()): Promise<void> {
    const propio = buildDeEstaPagina();
    if (!propio || disponible || enCurso || !navigator.onLine) return;
    if (ahora - ultima < INTERVALO_MINIMO_MS) return;
    enCurso = true;
    ultima = ahora;
    try {
        // `check` hace la URL única: ninguna caché puede contestar por el servidor.
        const respuesta = await $api.head(SONDA, { baseURL: '', params: { check: ahora } });
        const servidor = respuesta.headers[CABECERA];
        if (typeof servidor === 'string' && servidor && servidor !== propio) {
            avisarActualizacion();
        }
    } catch {
        // Sin red o con el servidor desplegando: se mira en la próxima vuelta.
    } finally {
        enCurso = false;
    }
}

/** Escucha los momentos en que una pestaña vieja vuelve a usarse. Devuelve la limpieza. */
export function vigilarActualizaciones(): () => void {
    const alVolver = () => {
        if (document.visibilityState === 'visible') comprobarActualizacion();
    };
    const alRestaurar = (evento: PageTransitionEvent) => {
        if (evento.persisted) comprobarActualizacion();
    };
    const alConectar = () => { comprobarActualizacion(); };

    document.addEventListener('visibilitychange', alVolver);
    window.addEventListener('pageshow', alRestaurar);
    window.addEventListener('online', alConectar);
    return () => {
        document.removeEventListener('visibilitychange', alVolver);
        window.removeEventListener('pageshow', alRestaurar);
        window.removeEventListener('online', alConectar);
    };
}

/** Un chunk JS o CSS que ya no existe en el servidor: hubo despliegue. */
export function esChunkPerdido(error: unknown): boolean {
    const { name, code } = (error ?? {}) as { name?: unknown; code?: unknown };
    return name === 'ChunkLoadError' || code === 'CSS_CHUNK_LOAD_FAILED';
}
