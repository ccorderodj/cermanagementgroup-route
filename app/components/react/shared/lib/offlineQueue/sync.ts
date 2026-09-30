import { $api } from '@/shared/api';
import {
    flushQueue,
    listPendingLocationEvidence,
    markLocationEvidenceFailed,
    removeLocationEvidence,
    type FlushResult,
    type PendingAction,
    type PendingLocationEvidence,
} from './offlineQueue';

/**
 * Un 4xx que no mejora repitiéndose. Misma regla que la cola de acciones.
 *
 * Importa especialmente aquí: un punto cuyo evento el servidor rechaza —porque
 * la acción operativa todavía no llegó— da **404**, y ése no es definitivo
 * desde el punto de vista del dispositivo: la acción está en la otra cola y
 * llegará. Así que el 404 se trata como transitorio a propósito, que es lo
 * contrario de lo que hace la cola de acciones.
 */
function esRechazoDefinitivoDeEvidencia(error: unknown): boolean {
    const estado = (error as { response?: { status?: number } })?.response?.status;
    if (typeof estado !== 'number') return false;
    // 404: el evento aún no existe en el servidor porque su acción sigue en la
    // cola. Reintentar **sí** sirve.
    // 408 y 429: el servidor pide esperar.
    if (estado === 404 || estado === 408 || estado === 429) return false;
    return estado >= 400 && estado < 500;
}

/**
 * Envía una entrada y sigue con la siguiente, **haya salido bien o mal**.
 *
 * Recursiva y no un bucle por la regla del proyecto, y la forma deja claro lo
 * que importa: a diferencia de `enviarEnOrden` para las acciones, aquí se
 * continúa tras un fallo. Un punto que el servidor rechaza no puede bloquear a
 * los demás, porque entre ellos no hay dependencia de orden.
 */
/**
 * Ata una entrada con sujeto pendiente a la fila que ya existe en el servidor.
 *
 * Devuelve el `payload` listo para enviar, o `null` si **no se puede
 * demostrar** a qué fila pertenece. Nunca adivina: §4 prohíbe atar por
 * proximidad, y "el que había" es una forma de proximidad.
 *
 * La condición para atar es estrecha a propósito: sólo si hay **una sola**
 * entrada pendiente de ese tipo de sujeto. Si el supervisor hizo dos viajes sin
 * red, dos puntos de `start_trip` competirían por el mismo `trip.id` y
 * cualquiera de los dos podría ser el equivocado; en ese caso no se ata
 * ninguno y el barrido del servidor los declara Missing, que es la respuesta
 * veraz.
 */
async function resolverSujeto(
    entrada: PendingLocationEvidence,
    pendientes: PendingLocationEvidence[],
): Promise<Record<string, unknown> | null> {
    if (!entrada.subjectPending) return entrada.payload;

    const competidoras = pendientes.filter(
        (otra) => otra.subjectPending === entrada.subjectPending,
    ).length;
    if (competidoras > 1) return null;

    let actual: {
        work_session?: { id: number } | null;
        current_trip?: { id: number } | null;
    };
    try {
        actual = (await $api.get('/worksessions/current')).data;
    } catch {
        // Sin servidor no se puede resolver todavía. Se deja pendiente.
        return null;
    }

    const fila = entrada.subjectPending === 'work_session'
        ? actual?.work_session
        : actual?.current_trip;
    if (!fila?.id) return null;

    return { ...entrada.payload, subject_id: fila.id };
}

async function enviarEvidencia(
    pendientes: PendingLocationEvidence[],
    indice: number,
    sincronizadas: number,
    fallidas: number,
): Promise<{ synced: number; failed: number }> {
    if (indice >= pendientes.length) {
        return { synced: sincronizadas, failed: fallidas };
    }
    const entrada = pendientes[indice];
    const resuelto = await resolverSujeto(entrada, pendientes);
    if (resuelto === null) {
        // Todavía no se puede atar. Se conserva y se reintenta al siguiente
        // vaciado; no se descarta y no se ata a lo que no se puede probar.
        return enviarEvidencia(pendientes, indice + 1, sincronizadas, fallidas + 1);
    }
    try {
        await $api.post(entrada.endpoint, resuelto);
        await removeLocationEvidence(entrada.id);
        return enviarEvidencia(pendientes, indice + 1, sincronizadas + 1, fallidas);
    } catch (error) {
        const mensaje = error instanceof Error ? error.message : String(error);
        if (esRechazoDefinitivoDeEvidencia(error)) {
            // El servidor la rechazó a ella y no va a cambiar de opinión. Se
            // retira para no reintentarla eternamente; el evento queda sin
            // punto y el barrido del servidor lo cerrará.
            await removeLocationEvidence(entrada.id).catch(() => {});
        } else {
            await markLocationEvidenceFailed(entrada.id, mensaje).catch(() => {});
        }
        return enviarEvidencia(pendientes, indice + 1, sincronizadas, fallidas + 1);
    }
}

/**
 * Vacía la evidencia de ubicación pendiente. **No se detiene en el primero que
 * falla**, y ésa es la diferencia con la cola de acciones.
 *
 * Las acciones se paran en el primer fallo porque el orden es la propiedad que
 * importa: un `Arrived` aplicado antes de su `Start Trip` es un estado que el
 * dominio no puede producir. La evidencia de ubicación no tiene ese requisito
 * —cada punto va atado a su evento por la tupla de correlación— así que pararse
 * sólo conseguiría que un punto rechazado bloqueara a los demás.
 *
 * Nunca lanza: esto se llama desde caminos operativos y un fallo de ubicación
 * no puede propagarse a ellos (§12).
 */
export async function flushPendingLocationEvidence(): Promise<{
    synced: number;
    failed: number;
}> {
    let pendientes: PendingLocationEvidence[] = [];
    try {
        pendientes = await listPendingLocationEvidence();
    } catch {
        return { synced: 0, failed: 0 };
    }

    return enviarEvidencia(pendientes, 0, 0, 0);
}

/**
 * El vaciado de la cola. **Uno**, no uno por dominio.
 *
 * `offlineQueue.ts` sigue sin saber qué es HTTP: recibe el emisor y se ocupa
 * del orden y de la durabilidad. Aquí está el emisor, y está aquí —en `shared`
 * y no dentro de una entidad— porque la cola es una sola. Cuando la Jornada la
 * vaciaba por su cuenta y la Parada quiso enviar lo suyo, la única forma de
 * reutilizar ese emisor era que una entidad importara a la otra, y esas dos ya
 * se referencian en sentido contrario: el ciclo dejaba un esquema de Zod a
 * medio construir en tiempo de carga.
 *
 * `Idempotency-Key` es el identificador de la propia acción, así que reenviarla
 * tras un corte no repite la escritura.
 */
export async function flushPendingActions(): Promise<FlushResult> {
    // La evidencia de ubicación se vacía **después** de las acciones, no antes:
    // un punto sólo se puede atar a su evento cuando el evento existe en el
    // servidor, y el evento llega por la cola de acciones. Al revés, cada
    // reconexión desperdiciaría un intento por punto.
    const resultado = await flushQueue(async (accion: PendingAction) => {
        await $api.request({
            url: accion.endpoint,
            method: accion.method,
            data: accion.payload,
            headers: { 'Idempotency-Key': accion.id },
        });
    });
    await flushPendingLocationEvidence();
    return resultado;
}

/**
 * Envía una acción recién encolada y devuelve su rechazo, si el servidor la
 * rechazó **a ella**.
 *
 * Distinguir de quién es el rechazo importa: el vaciado se detiene en la
 * primera que falla, así que un 409 puede pertenecer a algo encolado antes.
 * Atribuirlo a la acción actual mostraría al supervisor un error que no es el
 * suyo sobre una acción que sigue pendiente.
 */
export async function submitAction(accion: PendingAction): Promise<void> {
    const resultado = await flushPendingActions();
    if (resultado.rejected?.id === accion.id) {
        throw resultado.rejectedError;
    }
}
