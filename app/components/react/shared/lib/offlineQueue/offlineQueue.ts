/**
 * Cola de acciones durable, independiente de la sesión (RTE03, §14).
 *
 * El requisito que resuelve: una acción que la interfaz da por aceptada tiene
 * que sobrevivir a que la aplicación se cierre, el teléfono se apague o la
 * cookie de sesión caduque, y tiene que aplicarse **una sola vez** aunque se
 * reenvíe. IndexedDB es el almacén — sobrevive a recargar la página y a
 * cerrar el navegador, que es justo lo que `localStorage` también haría, pero
 * de forma asíncrona y sin el límite de ~5 MB que empieza a doler el día que
 * esto guarde algo más que dos acciones.
 *
 * Genérico a propósito: no sabe qué es una Jornada. RTE03 la usa para
 * `Start Work`/`End Work`; RTE04 la reutilizará para Trip sin tocar este
 * archivo — es el "cimiento reutilizable" que piden las instrucciones,
 * exactamente en el sentido en que `app/core` aloja primitivos de la
 * plataforma y no de un dominio.
 *
 * Durabilidad, con el límite dicho con honestidad
 * --------------------------------------------------
 * Una acción se escribe en IndexedDB **antes** de que la interfaz la
 * enseñe como aceptada (ver `enqueueAction`). Eso la protege de: cerrar la
 * pestaña, matar la aplicación, perder la cobertura de red, o que la cookie
 * de sesión caduque mientras está en cola. **No** la protege de: que la
 * persona borre los datos del sitio, que el navegador expulse el
 * almacenamiento bajo presión de espacio, que se desinstale la aplicación, o
 * que el dispositivo se pierda o se destruya. Son límites reales, no un
 * defecto que se calle.
 *
 * Idempotencia
 * ------------
 * Cada acción nace con un identificador propio (`crypto.randomUUID()`) que
 * viaja como `Idempotency-Key` en la petición HTTP. El servidor reutiliza el
 * mecanismo existente (`app/core/integration/idempotency.py`): reenviar la
 * misma clave devuelve la misma respuesta sin repetir la escritura. La cola
 * puede reintentar sin miedo a duplicar nada.
 *
 * Orden
 * -----
 * `sequence` es un contador monótono por dispositivo. El vaciado procesa las
 * acciones en ese orden y **se detiene** en el primer fallo en vez de saltar
 * a la siguiente: una `Jornada` terminada antes de empezar, por haberse
 * reordenado, sería un estado que el dominio nunca podría producir por sí
 * mismo.
 */

const DATABASE_NAME = 'cer-route-offline';
const DATABASE_VERSION = 1;
const STORE_NAME = 'pending_actions';

export type PendingActionStatus = 'pending' | 'failed';

export interface PendingAction {
    /** También la `Idempotency-Key` que recibe el servidor. */
    id: string;
    /** Orden de creación en este dispositivo. */
    sequence: number;
    /** Qué endpoint golpear. Nunca incluye datos de sesión: esos van en la cookie. */
    endpoint: string;
    method: 'POST';
    payload: Record<string, unknown>;
    /** Para que la interfaz pueda explicar qué es cada fila pendiente. */
    kind: string;
    createdAt: string;
    status: PendingActionStatus;
    /** Presente solo si `status === 'failed'`: por qué se detuvo la cola. */
    lastError?: string;
}

let dbPromise: Promise<IDBDatabase> | null = null;

function openDatabase(): Promise<IDBDatabase> {
    if (dbPromise) return dbPromise;

    dbPromise = new Promise((resolve, reject) => {
        const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);

        request.onupgradeneeded = () => {
            const db = request.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' });
                store.createIndex('by_sequence', 'sequence', { unique: true });
            }
        };

        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });

    return dbPromise;
}

async function withStore<T>(
    mode: IDBTransactionMode,
    run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, mode);
        const store = tx.objectStore(STORE_NAME);
        const request = run(store);

        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

export async function listPendingActions(): Promise<PendingAction[]> {
    const todas = await withStore<PendingAction[]>('readonly', (store) => store.getAll());
    return todas.sort((a, b) => a.sequence - b.sequence);
}

let sequenceCounter = 0;

async function nextSequence(): Promise<number> {
    const existentes = await listPendingActions();
    sequenceCounter = existentes.reduce(
        (max, accion) => Math.max(max, accion.sequence),
        sequenceCounter,
    );
    sequenceCounter += 1;
    return sequenceCounter;
}

/**
 * Encola una acción. **Se resuelve solo después de que IndexedDB confirmó la
 * escritura** — es lo que hace que "aceptado por la interfaz" y "durable"
 * sean la misma cosa, y no dos pasos donde el segundo puede no llegar a
 * ocurrir.
 */
export async function enqueueAction(
    kind: string,
    endpoint: string,
    payload: Record<string, unknown>,
): Promise<PendingAction> {
    const accion: PendingAction = {
        id: crypto.randomUUID(),
        sequence: await nextSequence(),
        endpoint,
        method: 'POST',
        payload,
        kind,
        createdAt: new Date().toISOString(),
        status: 'pending',
    };

    await withStore('readwrite', (store) => store.add(accion));
    return accion;
}

export async function removeAction(id: string): Promise<void> {
    await withStore('readwrite', (store) => store.delete(id));
}

async function markFailed(id: string, error: string): Promise<void> {
    const accion = await withStore<PendingAction | undefined>('readonly', (store) => store.get(id));
    if (!accion) return;
    await withStore('readwrite', (store) => store.put({ ...accion, status: 'failed', lastError: error }));
}

export interface FlushResult {
    synced: string[];
    stoppedAt: string | null;
    stoppedReason: string | null;
}

/**
 * Envía una acción y avanza a la siguiente **solo si la anterior tuvo
 * éxito**. Recursiva en vez de un bucle: el orden es la propiedad que
 * importa —una `Jornada` terminada antes de empezar por haberse reordenado
 * es un estado que el dominio nunca podría producir por sí mismo—, y la
 * recursión secuencial la preserva exactamente igual que un `for`, sin uno.
 */
async function enviarEnOrden(
    pendientes: PendingAction[],
    indice: number,
    sendAction: (accion: PendingAction) => Promise<void>,
    sincronizadas: string[],
): Promise<FlushResult> {
    if (indice >= pendientes.length) {
        return { synced: sincronizadas, stoppedAt: null, stoppedReason: null };
    }

    const accion = pendientes[indice];

    try {
        await sendAction(accion);
        await removeAction(accion.id);
    } catch (error) {
        const mensaje = error instanceof Error ? error.message : String(error);
        await markFailed(accion.id, mensaje);
        return { synced: sincronizadas, stoppedAt: accion.id, stoppedReason: mensaje };
    }

    return enviarEnOrden(pendientes, indice + 1, sendAction, [...sincronizadas, accion.id]);
}

/**
 * Reenvía las acciones pendientes, en orden, deteniéndose en el primer
 * fallo. Segura de llamar varias veces: cada acción sincronizada se retira
 * de la cola, así que una segunda llamada solo ve lo que de verdad sigue
 * pendiente.
 */
export async function flushQueue(
    sendAction: (accion: PendingAction) => Promise<void>,
): Promise<FlushResult> {
    const pendientes = await listPendingActions();
    return enviarEnOrden(pendientes, 0, sendAction, []);
}
