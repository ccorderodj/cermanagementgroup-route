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
/**
 * 2 desde RTE06: se añadió el almacén de evidencia de ubicación.
 *
 * Misma base y mismo módulo a propósito. §7 de RTE06 prohíbe una segunda cola,
 * y esto no lo es: es el mismo mecanismo de durabilidad con **dos carriles**,
 * porque los dos datos tienen semánticas de orden distintas y meterlos en el
 * mismo carril rompería una de las dos.
 *
 * `onupgradeneeded` crea lo que falte y no toca lo que hay, así que un
 * dispositivo con la versión 1 y acciones pendientes las conserva.
 */
const DATABASE_VERSION = 2;
const STORE_NAME = 'pending_actions';
/**
 * Evidencia de ubicación pendiente de enviar.
 *
 * Carril aparte del de acciones por una razón concreta: el de acciones se
 * **detiene** en el primer fallo para no aplicar un `Arrived` antes que su
 * `Start Trip`. La ubicación no tiene ese requisito —cada punto va atado a su
 * evento por la tupla de correlación, y el servidor lo rechaza si el evento no
 * existe— y si compartieran carril, un punto que el servidor rechaza bloquearía
 * las acciones operativas que van detrás.
 */
const LOCATION_STORE = 'pending_location_evidence';

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
            if (!db.objectStoreNames.contains(LOCATION_STORE)) {
                // `id` es la tupla de correlación, así que guardar dos veces el
                // mismo evento **sobrescribe** en vez de duplicar: la
                // idempotencia empieza en el dispositivo y no depende de que el
                // servidor la arregle después.
                db.createObjectStore(LOCATION_STORE, { keyPath: 'id' });
            }
        };

        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });

    return dbPromise;
}

async function withNamedStore<T>(
    nombre: string,
    mode: IDBTransactionMode,
    run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(nombre, mode);
        const store = tx.objectStore(nombre);
        const request = run(store);

        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

async function withStore<T>(
    mode: IDBTransactionMode,
    run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
    return withNamedStore(STORE_NAME, mode, run);
}

/**
 * Un punto de ubicación esperando a poder enviarse.
 *
 * `id` es la tupla de correlación —`{event_kind}:{subject_id}`— y no un
 * identificador propio. Eso hace que reintentar el mismo evento reemplace la
 * entrada en vez de apilar otra, y que dos capturas del mismo evento en el
 * mismo dispositivo no puedan producir dos envíos.
 *
 * `payload` se guarda **tal cual se midió**, incluido `evidence_level` y
 * `device_captured_at`. Es lo que garantiza que un punto cacheado no se
 * convierta en fresco por subirse más tarde: nada recalcula esos campos al
 * enviar.
 */
export interface PendingLocationEvidence {
    id: string;
    /** `/location/evidence` o `/location/missing`. */
    endpoint: string;
    payload: Record<string, unknown>;
    createdAt: string;
    attempts: number;
    lastError?: string;
    /**
     * Cuando deja de tener sentido reintentar este envio.
     *
     * Sale de la ventana de recuperacion de la compania mas el margen del
     * barrido, que son los mismos numeros con los que el servidor decide
     * cerrar el hecho por su cuenta. Pasada esa hora ningun reintento puede
     * ganar: lo que haya que decir del evento lo dira el barrido.
     *
     * Es opcional porque las entradas guardadas antes de que esto existiera no
     * lo tienen. A esas se las sigue tratando como antes.
     */
    expiresAt?: string;
}

/** Guarda o reemplaza la evidencia pendiente de un evento. */
export async function enqueueLocationEvidence(
    id: string,
    endpoint: string,
    payload: Record<string, unknown>,
    expiresAt?: string,
): Promise<void> {
    const existente = await withNamedStore<PendingLocationEvidence | undefined>(
        LOCATION_STORE,
        'readonly',
        (store) => store.get(id) as IDBRequest<PendingLocationEvidence | undefined>,
    );
    const entrada: PendingLocationEvidence = {
        id,
        endpoint,
        payload,
        // Se conserva la fecha del primer intento: lo que importa es cuándo se
        // capturó, no cuándo se reintentó.
        createdAt: existente?.createdAt ?? new Date().toISOString(),
        attempts: existente?.attempts ?? 0,
        // Se conserva la caducidad del primer encolado por lo mismo que la
        // fecha: reencolar no estira el plazo que da el servidor.
        expiresAt: existente?.expiresAt ?? expiresAt,
    };
    await withNamedStore(LOCATION_STORE, 'readwrite', (store) => store.put(entrada));
}

export async function listPendingLocationEvidence(): Promise<
    PendingLocationEvidence[]
    > {
    const filas = await withNamedStore<PendingLocationEvidence[]>(
        LOCATION_STORE,
        'readonly',
        (store) => store.getAll() as IDBRequest<PendingLocationEvidence[]>,
    );
    // Por fecha de captura, que es el orden en que ocurrieron. No es un
    // requisito del dominio —el servidor correlaciona por la tupla, no por el
    // orden de llegada— pero hace el reenvío predecible y los logs legibles.
    return filas.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export async function removeLocationEvidence(id: string): Promise<void> {
    await withNamedStore(LOCATION_STORE, 'readwrite', (store) => store.delete(id));
}

export async function markLocationEvidenceFailed(
    id: string,
    error: string,
): Promise<void> {
    const entrada = await withNamedStore<PendingLocationEvidence | undefined>(
        LOCATION_STORE,
        'readonly',
        (store) => store.get(id) as IDBRequest<PendingLocationEvidence | undefined>,
    );
    if (!entrada) return;
    const actualizada: PendingLocationEvidence = {
        ...entrada,
        attempts: entrada.attempts + 1,
        lastError: error.slice(0, 300),
    };
    await withNamedStore(LOCATION_STORE, 'readwrite', (store) => store.put(actualizada));
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
    /** La acción que el servidor rechazó por sus méritos, si la hubo. */
    rejected: PendingAction | null;
    /** El error tal cual, para que quien llamó pueda leer su código. */
    rejectedError: unknown;
}

/**
 * Un rechazo del servidor no es un fallo de red.
 *
 * Reintentar tiene sentido cuando la acción **podría** salir bien más tarde:
 * sin cobertura, con un 5xx, o con un 408/429 que piden esperar. No lo tiene
 * cuando el servidor la evaluó y dijo que no: un 409 de "sigues en ruta" o un
 * 422 de "falta el dato" van a decir exactamente lo mismo dentro de una hora.
 *
 * Dejar esas en la cola era peor que inútil. `enviarEnOrden` se detiene en el
 * primer fallo para preservar el orden, así que una acción rechazada para
 * siempre **bloquea todo lo que venga detrás**: la jornada siguiente no se
 * abriría nunca. Y si algún día dejara de bloquear, sería peor aún — un
 * `End Work` que el supervisor descartó al elegir "seguir trabajando" se
 * reenviaría solo y le cerraría el día sin que nadie lo pidiera.
 *
 * Así que se retira de la cola y se devuelve a quien llamó, que es el único
 * que sabe qué hacer con un 409 concreto.
 */
function esRechazoDefinitivo(error: unknown): boolean {
    const estado = (error as { response?: { status?: number } })?.response?.status;
    if (typeof estado !== 'number') return false;
    if (estado === 408 || estado === 429) return false;
    return estado >= 400 && estado < 500;
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
        return {
            synced: sincronizadas,
            stoppedAt: null,
            stoppedReason: null,
            rejected: null,
            rejectedError: null,
        };
    }

    const accion = pendientes[indice];

    try {
        await sendAction(accion);
        await removeAction(accion.id);
    } catch (error) {
        const mensaje = error instanceof Error ? error.message : String(error);
        if (esRechazoDefinitivo(error)) {
            await removeAction(accion.id);
            return {
                synced: sincronizadas,
                stoppedAt: accion.id,
                stoppedReason: mensaje,
                rejected: accion,
                rejectedError: error,
            };
        }
        await markFailed(accion.id, mensaje);
        return {
            synced: sincronizadas,
            stoppedAt: accion.id,
            stoppedReason: mensaje,
            rejected: null,
            rejectedError: null,
        };
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
