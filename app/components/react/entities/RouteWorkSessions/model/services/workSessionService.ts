import { $api, parseApi } from '@/shared/api';
import {
    enqueueAction,
    flushPendingActions,
    type FlushResult,
    type PendingAction,
} from '@/shared/lib/offlineQueue';
import { captureTimeEvidence, deviceTimeZone } from '@/shared/lib/utils/utils';
import { currentWorkSessionSchema, type CurrentWorkSessionResponse } from '../types';

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

export async function fetchCurrentWorkSession(): Promise<CurrentWorkSessionResponse> {
    const response = await $api.get('/worksessions/current');
    return parseApi(currentWorkSessionSchema, response.data, 'fetchCurrentWorkSession');
}

export async function queueStartWork(): Promise<PendingAction> {
    // La zona viaja **sólo** aquí (T-1/T-2): fija la de la jornada. Se captura
    // al encolar, junto al instante, para que una acción que esperó sin red no
    // tome la zona del momento de sincronizar. Sin zona, el servidor fecha con
    // el desfase como antes: no se bloquea nada.
    const zona = deviceTimeZone();
    return enqueueAction('worksession.start', '/worksessions', {
        ...captureTimeEvidence(),
        ...(zona ? { time_zone: zona } : {}),
    });
}

/**
 * Cierra la jornada.
 *
 * `endAnyway` es la confirmación explícita del supervisor tras ver que todavía
 * está en ruta. Sin ella el servidor responde 409 y la pantalla ofrece seguir
 * trabajando o terminar de todos modos (D-07): no se cierra por descuido lo
 * que alguien dejó a medias.
 */
export async function queueEndWork(
    sessionId: number,
    endAnyway = false,
): Promise<PendingAction> {
    return enqueueAction(
        'worksession.end',
        `/worksessions/${sessionId}/end`,
        { ...captureTimeEvidence(), end_anyway: endAnyway },
    );
}

/**
 * Reenvía lo pendiente, en orden, con la clave de idempotencia de cada
 * acción. Segura de llamar tan seguido como haga falta: lo ya sincronizado
 * sale de la cola y no se reenvía.
 */
export async function syncPendingWorkSessionActions(): Promise<FlushResult> {
    return flushPendingActions();
}
