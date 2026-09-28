import { enqueueAction, submitAction } from '@/shared/lib/offlineQueue';
import { captureTimeEvidence } from '@/shared/lib/utils/utils';
import { type TerminalAction } from '../types';

/**
 * Los dos comandos de la parada: empezarla y cerrarla.
 *
 * Por qué se encolan
 * ------------------
 * Son órdenes deterministas y sin binarios —empezar, terminar, marcharse—, así
 * que usan la misma cola durable de RTE03. No hay una segunda: una acción que
 * la interfaz da por aceptada se escribe en IndexedDB antes de devolver el
 * control, y viaja con su hora de ocurrencia para que la duración de la parada
 * sea la real y no la de sincronizar.
 *
 * Por qué además se envían aquí
 * ------------------------------
 * Encolar y callar no sirve para estas dos. Empezar una parada puede chocar con
 * lo que el contexto exige y terminarla puede chocar con un bloque ya cerrado
 * desde otro dispositivo; el supervisor **está mirando la pantalla** en ese
 * momento, y descubrirlo al reconectar sería descubrirlo tarde. Así que se
 * vacía la cola en el acto y el rechazo del servidor se devuelve a quien llamó.
 *
 * Sin cobertura no hay rechazo que devolver: la acción se queda en la cola y se
 * enviará al volver la red. Eso es lo que hace que esto siga funcionando en una
 * zona sin señal, que es el motivo de que exista la cola.
 *
 * Cada acción lleva su identificador como `Idempotency-Key`, y el servidor es
 * idempotente por su cuenta: reintentar no crea una segunda parada ni reescribe
 * un resultado ya registrado.
 */

export async function queueStartActivity(
    tripId: number,
    activityIds: number[],
): Promise<void> {
    const accion = await enqueueAction(
        'activity.start',
        `/trips/${tripId}/activity/start`,
        { activity_ids: activityIds, ...captureTimeEvidence() },
    );
    await submitAction(accion);
}

interface CierreDeParada {
    action: TerminalAction;
    outcomeId: number;
    notes?: string | null;
    receivedById?: number | null;
}

export async function queueTerminalizeActivity(
    tripId: number,
    { action, outcomeId, notes, receivedById }: CierreDeParada,
): Promise<void> {
    const accion = await enqueueAction(
        `activity.${action}`,
        `/trips/${tripId}/activity/${action}`,
        {
            // El endpoint dice el verbo y el cuerpo lo repite: el servidor
            // compara los dos y rechaza el desacuerdo, para que una URL mal
            // formada no cierre una parada con la acción contraria.
            action,
            outcome_id: outcomeId,
            notes: notes?.trim() || null,
            received_by_id: receivedById ?? null,
            ...captureTimeEvidence(),
        },
    );
    await submitAction(accion);
}
