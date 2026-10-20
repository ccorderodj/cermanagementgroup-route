import { z } from 'zod';
import { $api, parseApi } from '@/shared/api';
import {
    currentQueueOwner,
    enqueueLocationSample,
    flushPendingLocationSamples,
    holdLocationSamples,
} from '@/shared/lib/offlineQueue';
import { pedirPosicion } from './location';

/**
 * Captura periódica de ubicación (RTE-LOC-02): un punto cada N segundos
 * mientras la jornada está activa **y la página está en condiciones de pedir la
 * ubicación**.
 *
 * Independiente de la captura por evento
 * --------------------------------------
 * No toca `captureFor` ni su política: reutiliza sólo la primitiva de lectura
 * (`pedirPosicion`) y tiene su propio carril de cola. Si algo de aquí falla, la
 * jornada sigue exactamente igual.
 *
 * Por qué `getCurrentPosition` cada N segundos y no `watchPosition`
 * -----------------------------------------------------------------
 * A 300 s, `watchPosition` mantendría el GPS encendido entre muestras para
 * nada: más batería y la misma información. Una lectura acotada (10 s, con un
 * punto de hasta 60 s de antigüedad) cada intervalo basta.
 *
 * Lo que no se promete
 * --------------------
 * Con la pantalla bloqueada, la pestaña en segundo plano o la aplicación
 * cerrada, el navegador suspende los temporizadores y la geolocalización. Al
 * volver a primer plano se comprueba si tocaba una muestra y se toma **una**
 * (nunca se rellenan las que faltaron: no hay puntos sintéticos).
 *
 * Una sola pestaña
 * ----------------
 * El muestreo corre dentro de un candado del navegador (`navigator.locks`) por
 * tenant, usuario y jornada: con dos pestañas abiertas, una muestrea y la otra
 * espera a que la primera se cierre.
 */

const policySchema = z.object({
    fresh_max_accuracy_m: z.number(),
    periodic_capture_enabled: z.boolean(),
    periodic_capture_interval_seconds: z.number(),
});

export interface ConfigPeriodica {
    enabled: boolean;
    intervalSeconds: number;
    maxAccuracyM: number;
}

/** El texto que se enseña cuando la compañía la tiene encendida (RTE-LOC-02 U1). */
export const PERIODIC_CAPTURE_NOTICE = 'CER Route records your location periodically while you use the app during your workday.';

/** Cuánto se espera a reconsultar la configuración cuando está apagada. */
const REVISION_APAGADA_MS = 60_000;
const LECTURA: PositionOptions = { enableHighAccuracy: true, timeout: 10_000, maximumAge: 60_000 };

/** Contadores técnicos, para pruebas y diagnóstico. Sin coordenadas. */
export const periodicStats = {
    captured: 0, skipped: 0, sent: 0, failed: 0, overflow: 0,
};

/** La configuración efectiva de la compañía, o `null` si no se pudo leer. */
export async function readPeriodicCaptureConfig(): Promise<ConfigPeriodica | null> {
    try {
        const respuesta = await $api.get('/location/policy', { timeout: 5_000 });
        const leida = parseApi(policySchema, respuesta.data, 'readPeriodicCapture');
        return {
            enabled: leida.periodic_capture_enabled,
            intervalSeconds: leida.periodic_capture_interval_seconds,
            maxAccuracyM: leida.fresh_max_accuracy_m,
        };
    } catch {
        return null;
    }
}

function claveDeUltima(owner: { userId: number; tenant: string }, sessionId: number): string {
    return `cer-route-periodic-last:${owner.tenant}:${owner.userId}:${sessionId}`;
}

function leerUltima(clave: string): number {
    try {
        return Number(window.localStorage.getItem(clave)) || 0;
    } catch {
        return 0;
    }
}

function guardarUltima(clave: string, instante: number): void {
    try {
        window.localStorage.setItem(clave, String(instante));
    } catch {
        // Sin almacenamiento, otra pestaña podría muestrear antes de tiempo;
        // el candado ya evita que sean dos a la vez.
    }
}

async function tomarMuestra(sessionId: number, config: ConfigPeriodica): Promise<void> {
    try {
        const punto = await pedirPosicion(LECTURA);
        if (punto.accuracy === null || punto.accuracy > config.maxAccuracyM) {
            periodicStats.skipped += 1;
            return;
        }
        const guardada = await enqueueLocationSample(sessionId, {
            client_sample_id: crypto.randomUUID(),
            latitude: punto.latitude.toFixed(6),
            longitude: punto.longitude.toFixed(7),
            accuracy_m: punto.accuracy.toFixed(2),
            device_captured_at: new Date(punto.timestamp).toISOString(),
        });
        if (guardada) periodicStats.captured += 1;
        else periodicStats.overflow += 1;
    } catch {
        // Sin señal, sin permiso o sin respuesta: esta vez no hay muestra.
        periodicStats.skipped += 1;
    }
}

/**
 * Arranca el muestreo de una jornada. Devuelve la función que lo para.
 *
 * Se para al llamarla (End Work, desmontaje de My Route, permiso revocado,
 * logout o cambio de usuario: todos desmontan o cambian la jornada) y en cuanto
 * la configuración dice apagado.
 */
export function startPeriodicSampling(sessionId: number): () => void {
    const owner = currentQueueOwner();
    if (!owner) return () => {};
    const clave = claveDeUltima(owner, sessionId);
    let parado = false;
    let despertar: (() => void) | null = null;
    const cancelar = new AbortController();

    const alVolver = () => {
        if (document.visibilityState === 'visible') despertar?.();
    };
    document.addEventListener('visibilitychange', alVolver);

    const esperar = (ms: number) => new Promise<void>((resolver) => {
        const reloj = window.setTimeout(resolver, ms);
        despertar = () => {
            window.clearTimeout(reloj);
            resolver();
        };
    });

    const ciclo = async (): Promise<void> => {
        if (parado) return;
        const config = await readPeriodicCaptureConfig();
        if (parado) return;
        if (!config || !config.enabled) {
            if (config && !config.enabled) await holdLocationSamples().catch(() => {});
            await esperar(REVISION_APAGADA_MS);
            await ciclo();
            return;
        }
        const intervalo = config.intervalSeconds * 1000;
        const toca = leerUltima(clave) + intervalo;
        if (Date.now() >= toca && document.visibilityState === 'visible') {
            guardarUltima(clave, Date.now());
            await tomarMuestra(sessionId, config);
            const envio = await flushPendingLocationSamples();
            periodicStats.sent += envio.sent;
            periodicStats.failed += envio.failed;
        }
        if (parado) return;
        await esperar(Math.max(1_000, leerUltima(clave) + intervalo - Date.now()));
        await ciclo();
    };

    const correr = () => ciclo().catch(() => {});
    if (navigator.locks?.request) {
        navigator.locks
            .request(`cer-route-periodic:${owner.tenant}:${owner.userId}:${sessionId}`, { signal: cancelar.signal }, correr)
            .catch(() => {});
    } else {
        correr();
    }

    return () => {
        parado = true;
        cancelar.abort();
        despertar?.();
        document.removeEventListener('visibilitychange', alVolver);
    };
}
