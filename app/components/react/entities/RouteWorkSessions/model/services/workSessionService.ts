import { $api, parseApi } from '@/shared/api';
import { enqueueAction, flushQueue, type FlushResult, type PendingAction } from '@/shared/lib/offlineQueue';
import { currentWorkSessionSchema, type CurrentWorkSessionResponse, type TimeEvidence } from '../types';

/**
 * Servicio de la Jornada: lectura directa, escritura siempre por la cola.
 *
 * `Start Work` y `End Work` **nunca** llaman a `$api` directamente. Pasan
 * primero por `enqueueAction` —que confirma la escritura en IndexedDB antes
 * de devolver el control— y solo después se intenta el envío. Con
 * conectividad, el envío ocurre en el mismo instante y la diferencia con una
 * llamada directa es imperceptible; sin ella, la acción queda en la cola y
 * `syncPendingWorkSessionActions` la reintenta cuando vuelva la red o tras
 * reautenticarse (§14 de las instrucciones RTE03).
 */

function captureTimeEvidence(): TimeEvidence {
    return {
        device_captured_at: new Date().toISOString(),
        // `getTimezoneOffset()` devuelve minutos al OESTE de UTC; el backend
        // espera minutos al ESTE (D-10), de ahí el signo invertido.
        utc_offset_minutes: -new Date().getTimezoneOffset(),
    };
}

export async function fetchCurrentWorkSession(): Promise<CurrentWorkSessionResponse> {
    const response = await $api.get('/worksessions/current');
    return parseApi(currentWorkSessionSchema, response.data, 'fetchCurrentWorkSession');
}

export async function queueStartWork(): Promise<PendingAction> {
    return enqueueAction('worksession.start', '/worksessions', { ...captureTimeEvidence() });
}

export async function queueEndWork(sessionId: number): Promise<PendingAction> {
    return enqueueAction(
        'worksession.end',
        `/worksessions/${sessionId}/end`,
        { ...captureTimeEvidence() },
    );
}

/**
 * Reenvía lo pendiente, en orden, con la clave de idempotencia de cada
 * acción. Segura de llamar tan seguido como haga falta: lo ya sincronizado
 * sale de la cola y no se reenvía.
 */
export async function syncPendingWorkSessionActions(): Promise<FlushResult> {
    return flushQueue(async (accion) => {
        await $api.request({
            url: accion.endpoint,
            method: accion.method,
            data: accion.payload,
            headers: { 'Idempotency-Key': accion.id },
        });
    });
}
