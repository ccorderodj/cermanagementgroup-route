/**
 * Captura de ubicación: silenciosa, no bloqueante y por etapas (RTE06-CP2).
 *
 * La regla que manda sobre todas
 * ------------------------------
 * La acción operativa **no espera** a esto. §11 lo dice con esas palabras y §36
 * lo repite prohibiendo cualquier spinner que bloquee. Así que
 * `captureFor(...)` no se espera con `await` desde el flujo del supervisor: se
 * lanza y se olvida. Si el GPS tarda quince segundos, el supervisor ya está en
 * la pantalla siguiente.
 *
 * Y nada de esto se ve
 * --------------------
 * §12 enumera lo que **no** se muestra: "GPS captured", "GPS failed",
 * "location unavailable", timeout, aviso de precisión, estado del reintento,
 * "Missing Location". Ninguna función de este módulo devuelve algo que la
 * interfaz deba pintar. Los fallos se registran en el servidor y se quedan ahí:
 * quien tiene que enterarse es el administrador, no el supervisor que está
 * trabajando.
 *
 * Las etapas, en orden
 * --------------------
 * 1. posición actual con alta precisión, acotada por `freshTimeoutSeconds`;
 * 2. si falla, el último punto conocido que el navegador quiera dar, aceptado
 *    **sólo** si cumple frescura y precisión configuradas → `degraded_cached`;
 * 3. si no hay punto válido, una ventana de recuperación acotada en segundo
 *    plano → `recovered` si llega algo;
 * 4. agotadas las etapas, se declara Missing en el servidor.
 *
 * El nivel se decide **al escribir** y no se reconstruye después (§11): un
 * punto cacheado que se sube tarde sigue siendo cacheado.
 *
 * Por qué no usa la cola offline
 * ------------------------------
 * La cola de RTE03 preserva el **orden** de las acciones operativas, y se
 * detiene en la primera que falla para no aplicar un `Arrived` antes que su
 * `Start Trip`. La evidencia de ubicación no tiene ese requisito —cada punto va
 * atado a su evento por la tupla de correlación, y el servidor la rechaza si el
 * evento no existe— y meterla en la misma cola le pondría por delante de
 * acciones operativas un tráfico que puede esperar. Se reintenta sola, sin
 * bloquear a nadie.
 */

import { enqueueLocationEvidence } from '@/shared/lib/offlineQueue';
import { flushPendingLocationEvidence } from '@/shared/lib/offlineQueue/sync';

/** Los siete eventos de §10. `start_activity` no está, y es deliberado. */
export type LocationEventKind =
    | 'start_work'
    | 'start_trip'
    | 'change_plan'
    | 'arrived'
    | 'activity_complete'
    | 'activity_leave'
    | 'end_work';

/** Los umbrales del servidor. Se piden una vez y se recuerdan. */
interface LocationPolicy {
    freshTimeoutSeconds: number;
    freshMaxAccuracyM: number;
    cachedMaxAgeSeconds: number;
    cachedMaxAccuracyM: number;
    recoveryWindowSeconds: number;
}

/**
 * Los mismos valores por defecto que `RouteLocationPolicy` en el servidor.
 *
 * Están duplicados a propósito y el duplicado es acotado: si la petición de
 * política falla, la captura sigue funcionando con números razonables en vez de
 * quedarse sin capturar. El servidor vuelve a comprobar los criterios al
 * recibir, así que un cliente desactualizado no puede colar un punto que la
 * compañía no aceptaría — sólo desperdiciar un envío.
 */
const POLICY_POR_DEFECTO: LocationPolicy = {
    freshTimeoutSeconds: 10,
    freshMaxAccuracyM: 100,
    cachedMaxAgeSeconds: 300,
    cachedMaxAccuracyM: 500,
    recoveryWindowSeconds: 180,
};

let politica: LocationPolicy = POLICY_POR_DEFECTO;

/** Sustituye los umbrales. La llama el arranque de la página de ejecución. */
export function setLocationPolicy(parcial: Partial<LocationPolicy>): void {
    politica = { ...POLICY_POR_DEFECTO, ...parcial };
}

interface Intento {
    stage: string;
    started_at: string;
    duration_ms: number;
    error_code?: number;
    error_message?: string;
}

type EstadoDelPermiso = 'granted' | 'denied' | 'prompt' | 'unavailable';

/**
 * Qué dice el navegador del permiso, sin interpretarlo.
 *
 * §29 prohíbe inventar causas que la plataforma no pueda demostrar. Esto
 * devuelve el estado tal cual, y `unavailable` cuando la Permissions API no
 * existe — que es un hecho sobre el navegador, no sobre el GPS.
 */
async function leerPermiso(): Promise<EstadoDelPermiso> {
    try {
        if (!navigator.permissions?.query) return 'unavailable';
        const estado = await navigator.permissions.query({
            name: 'geolocation' as PermissionName,
        });
        return estado.state as EstadoDelPermiso;
    } catch {
        return 'unavailable';
    }
}

/**
 * Respiro entre intentos de recuperación.
 *
 * La ventana se acota por tiempo, no por número de intentos, así que sin esto
 * un proveedor que responde al instante la convertiría en un bucle ocupado.
 * Dos segundos dan margen al GPS para fijar algún satélite más, que es la
 * razón por la que reintentar sirve de algo.
 */
const PAUSA_ENTRE_INTENTOS_MS = 2000;

interface PuntoCrudo {
    latitude: number;
    longitude: number;
    accuracy: number | null;
    timestamp: number;
}

function normalizar(posicion: GeolocationPosition): PuntoCrudo {
    return {
        latitude: posicion.coords.latitude,
        longitude: posicion.coords.longitude,
        accuracy: Number.isFinite(posicion.coords.accuracy)
            ? posicion.coords.accuracy
            : null,
        timestamp: posicion.timestamp,
    };
}

/** Una lectura de posición, envuelta en promesa y acotada en tiempo. */
function pedirPosicion(opciones: PositionOptions): Promise<PuntoCrudo> {
    return new Promise((resolver, rechazar) => {
        if (!navigator.geolocation) {
            // Un `Error` con `code`, no un objeto pelado: el resto del módulo
            // lee `code` para clasificar el fallo, y la regla del proyecto es
            // rechazar con `Error`. El código 0 no existe en la Geolocation
            // API, así que no colisiona con los suyos (1, 2, 3).
            const fallo = Object.assign(
                new Error('Geolocation is not available'),
                { code: 0 },
            );
            rechazar(fallo);
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (posicion) => resolver(normalizar(posicion)),
            (error) => rechazar(error),
            opciones,
        );
    });
}

/** Coordenadas con la precisión que el servidor acepta: 6 y 7 decimales. */
function aPayload(punto: PuntoCrudo) {
    return {
        latitude: punto.latitude.toFixed(6),
        longitude: punto.longitude.toFixed(7),
        accuracy_m: punto.accuracy === null ? undefined : punto.accuracy.toFixed(2),
        device_captured_at: new Date(punto.timestamp).toISOString(),
    };
}

/**
 * La llave de correlación, igual que la del servidor.
 *
 * Es lo que hace que guardar dos veces el mismo evento **reemplace** en vez de
 * duplicar: la idempotencia empieza en el dispositivo y no depende de que el
 * servidor la arregle después.
 */
export type Sujeto = { subjectId: number } | { clientActionKey: string };

function llaveDe(eventKind: LocationEventKind, subject: Sujeto): string {
    return 'clientActionKey' in subject
        ? `${eventKind}:key:${subject.clientActionKey}`
        : `${eventKind}:${subject.subjectId}`;
}

/** Lo que va en el cuerpo. El servidor exige exactamente una de las dos formas. */
function identidadDe(subject: Sujeto): Record<string, unknown> {
    return 'clientActionKey' in subject
        ? { client_action_key: subject.clientActionKey }
        : { subject_id: subject.subjectId };
}

/**
 * Guarda el punto **antes** de intentar enviarlo, y luego intenta.
 *
 * Éste es el cambio que exige el cierre de RTE06. Antes se llamaba a `$api`
 * directamente: sin red, la promesa se rechazaba, el `catch` de arriba la
 * tragaba en silencio y la evidencia **se perdía** — un punto que el
 * dispositivo sí había medido. Ahora se escribe en IndexedDB primero, así que
 * el peor caso es que se envíe más tarde.
 *
 * El `payload` se guarda tal cual se midió, `evidence_level` y
 * `device_captured_at` incluidos. Nada los recalcula al enviar, que es lo que
 * garantiza que un punto cacheado no se convierta en fresco por subirse tarde.
 */
async function enviarPunto(
    eventKind: LocationEventKind,
    subject: Sujeto,
    nivel: 'fresh' | 'degraded_cached' | 'recovered',
    punto: PuntoCrudo,
    permiso: EstadoDelPermiso,
    edadSegundos?: number,
): Promise<void> {
    const llave = llaveDe(eventKind, subject);
    await enqueueLocationEvidence(llave, '/location/evidence', {
        event_kind: eventKind,
        ...identidadDe(subject),
        evidence_level: nivel,
        ...aPayload(punto),
        ...(nivel === 'degraded_cached' ? { source_age_seconds: edadSegundos } : {}),
        permission_state: permiso,
    });
    await flushPendingLocationEvidence();
}

/**
 * Declara Missing, también de forma durable.
 *
 * Con la misma llave que el punto: si el punto llega después —porque la
 * recuperación tuvo éxito en otro intento— reemplaza al Missing en el almacén
 * en vez de coexistir con él. El servidor rechazaría el Missing de todas formas
 * (el punto manda), pero dejar los dos en el dispositivo enviaría una petición
 * que se sabe que va a fallar.
 */
async function declararMissing(
    eventKind: LocationEventKind,
    subject: Sujeto,
    razon: string,
    intentos: Intento[],
    permiso: EstadoDelPermiso,
    rechazado?: { age_seconds?: number; accuracy_m?: number },
): Promise<void> {
    const llave = llaveDe(eventKind, subject);
    await enqueueLocationEvidence(llave, '/location/missing', {
        event_kind: eventKind,
        ...identidadDe(subject),
        reason_code: razon,
        permission_state: permiso,
        attempts: intentos.slice(0, 20),
        ...(rechazado?.age_seconds !== undefined
            ? { rejected_age_seconds: rechazado.age_seconds }
            : {}),
        ...(rechazado?.accuracy_m !== undefined
            ? { rejected_accuracy_m: rechazado.accuracy_m.toFixed(2) }
            : {}),
    });
    await flushPendingLocationEvidence();
}

/**
 * De un error de la Geolocation API al código de razón del servidor.
 *
 * Los tres códigos son los del estándar: 1 permiso denegado, 2 posición no
 * disponible, 3 timeout. Nada más se deduce: §29 prohíbe inventar causas.
 */
function razonDe(codigo: number | undefined): string {
    if (codigo === 1) return 'permission_denied';
    if (codigo === 2) return 'position_unavailable';
    if (codigo === 3) return 'acquisition_timeout';
    return 'recovery_window_exhausted';
}

async function capturar(
    eventKind: LocationEventKind,
    subject: Sujeto,
): Promise<void> {
    const permiso = await leerPermiso();
    const intentos: Intento[] = [];

    // ── Etapa 1: posición actual ───────────────────────────────────────────
    const inicioFresco = Date.now();
    try {
        const punto = await pedirPosicion({
            enableHighAccuracy: true,
            timeout: politica.freshTimeoutSeconds * 1000,
            maximumAge: 0,
        });
        // En una variable propia, no leyendo `punto.accuracy` dos veces: así
        // TypeScript sabe que tras el `return` es un número, y el mensaje de
        // abajo puede decir cuánto era sin inventar un 0.
        const precision = punto.accuracy;
        const aceptable = precision === null
            || precision <= politica.freshMaxAccuracyM;
        if (aceptable) {
            await enviarPunto(
                eventKind,
                subject,
                'fresh',
                punto,
                permiso,
            );
            return;
        }
        // Se midió ahora pero con demasiado error. No es fresco utilizable, y
        // tampoco cacheado: se deja constancia y se sigue a la siguiente etapa.
        intentos.push({
            stage: 'current',
            started_at: new Date(inicioFresco).toISOString(),
            duration_ms: Date.now() - inicioFresco,
            error_message: `accuracy ${Math.round(precision)}m above threshold`,
        });
    } catch (error) {
        const fallo = error as GeolocationPositionError;
        intentos.push({
            stage: 'current',
            started_at: new Date(inicioFresco).toISOString(),
            duration_ms: Date.now() - inicioFresco,
            error_code: fallo?.code,
            error_message: fallo?.message?.slice(0, 300),
        });
        if (fallo?.code === 1) {
            // Permiso denegado: pedir la caché daría el mismo error. Se salta
            // a Missing sin gastar la ventana de recuperación en algo que no
            // puede funcionar.
            await declararMissing(
                eventKind,
                subject,
                'permission_denied',
                intentos,
                permiso,
            );
            return;
        }
    }

    // ── Etapa 2: el último punto conocido, si sirve ────────────────────────
    const inicioCache = Date.now();
    let rechazado: { age_seconds?: number; accuracy_m?: number } | undefined;
    try {
        const punto = await pedirPosicion({
            enableHighAccuracy: false,
            timeout: 3000,
            maximumAge: politica.cachedMaxAgeSeconds * 1000,
        });
        const edad = Math.max(0, Math.round((Date.now() - punto.timestamp) / 1000));
        const dentroDeEdad = edad <= politica.cachedMaxAgeSeconds;
        const dentroDePrecision = punto.accuracy === null
            || punto.accuracy <= politica.cachedMaxAccuracyM;
        const suficiente = dentroDeEdad && dentroDePrecision;
        if (suficiente) {
            await enviarPunto(
                eventKind,
                subject,
                'degraded_cached',
                punto,
                permiso,
                edad,
            );
            return;
        }
        // Había punto y no valía. Se guarda **su edad y su precisión**, nunca
        // dónde estaba: eso explica el fallo sin conservar una ubicación que el
        // sistema decidió no usar.
        rechazado = {
            age_seconds: edad,
            accuracy_m: punto.accuracy ?? undefined,
        };
        intentos.push({
            stage: 'cached',
            started_at: new Date(inicioCache).toISOString(),
            duration_ms: Date.now() - inicioCache,
            error_message: `cached point rejected: age ${edad}s`,
        });
    } catch (error) {
        const fallo = error as GeolocationPositionError;
        intentos.push({
            stage: 'cached',
            started_at: new Date(inicioCache).toISOString(),
            duration_ms: Date.now() - inicioCache,
            error_code: fallo?.code,
            error_message: fallo?.message?.slice(0, 300),
        });
    }

    // ── Etapa 3: la ventana de recuperación ───────────────────────────────
    //
    // Reintenta **hasta que la ventana se agote**, no una sola vez.
    //
    // Antes era un único `pedirPosicion` con el ancho de la ventana como
    // timeout, y sin comprobar la precisión: lo que devolviera se aceptaba
    // como `recovered`. Un punto rechazado en la etapa 1 por tener 2 km de
    // error entraba aquí como evidencia autoritativa, y `for_trip_waypoints`
    // no vuelve a filtrar por nivel ni por precisión, así que acababa siendo
    // un waypoint oficial de kilometraje. Era el nivel más lento de obtener
    // y el único sin exigencia (F-1).
    //
    // Ahora se exige **el mismo umbral que `fresh`**: un punto recuperado no
    // puede ser de peor calidad que uno recién capturado sólo por haber
    // tardado más. Se reutiliza `freshMaxAccuracyM` a propósito, en vez de
    // añadir un segundo umbral configurable: dos números que significan lo
    // mismo acaban divergiendo, y entonces nadie sabe cuál manda.
    //
    // Que un candidato no valga **no cierra la ventana**: mientras quede
    // tiempo se vuelve a intentar, porque el GPS suele mejorar según fija
    // satélites. Lo que cierra la ventana es el reloj.
    const inicioRecuperacion = Date.now();
    const finDeVentana = inicioRecuperacion + politica.recoveryWindowSeconds * 1000;
    // Precisión del mejor candidato rechazado, para que el Missing pueda
    // decir **cuánto** fallaba. Nunca se guarda dónde estaba.
    let mejorPrecisionRechazada: number | null = null;
    let huboCandidato = false;
    let ultimoFallo: GeolocationPositionError | undefined;

    // Los `await` de dentro son secuenciales **a propósito**: cada intento
    // tiene que terminar antes de decidir si queda ventana para el siguiente,
    // y lanzarlos en paralelo convertiría un reintento acotado en una ráfaga
    // de peticiones de posición simultáneas.
    /* eslint-disable no-await-in-loop */
    while (Date.now() < finDeVentana) {
        const inicioIntento = Date.now();
        const restante = finDeVentana - inicioIntento;
        try {
            const punto = await pedirPosicion({
                enableHighAccuracy: true,
                // Lo que quede de ventana, nunca más: el timeout no puede
                // sobrevivir a la ventana que lo acota.
                timeout: restante,
                maximumAge: 0,
            });
            huboCandidato = true;
            const precision = punto.accuracy;
            if (precision === null || precision <= politica.freshMaxAccuracyM) {
                // Se envía con **su** hora de captura, que es posterior al
                // evento. Es correcto y es el punto de `recovered`: la hora
                // dice cuándo se midió, no cuándo ocurrió el evento (§11).
                await enviarPunto(
                    eventKind,
                    subject,
                    'recovered',
                    punto,
                    permiso,
                );
                return;
            }
            // Midió, pero con demasiado error. Se deja constancia de **cuánto**
            // y se sigue intentando. Las coordenadas no se guardan: §12 y la
            // regla de privacidad ya aprobada para el candidato cacheado.
            if (
                mejorPrecisionRechazada === null
                || precision < mejorPrecisionRechazada
            ) {
                mejorPrecisionRechazada = precision;
            }
            intentos.push({
                stage: 'recovery',
                started_at: new Date(inicioIntento).toISOString(),
                duration_ms: Date.now() - inicioIntento,
                error_message:
                    `accuracy ${Math.round(precision)}m above threshold`,
            });
        } catch (error) {
            const fallo = error as GeolocationPositionError;
            ultimoFallo = fallo;
            intentos.push({
                stage: 'recovery',
                started_at: new Date(inicioIntento).toISOString(),
                duration_ms: Date.now() - inicioIntento,
                error_code: fallo?.code,
                error_message: fallo?.message?.slice(0, 300),
            });
            // El permiso denegado no mejora esperando: cortar aquí evita
            // consumir la ventana entera preguntando lo mismo.
            if (fallo?.code === 1) break;
        }

        // Respiro entre intentos. Sin esto, un proveedor que responde al
        // instante convertiría la ventana en un bucle ocupado —GEO-04 lo
        // prohíbe— y gastaría batería sin mejorar la fijación.
        const consumido = Date.now() - inicioIntento;
        if (consumido < PAUSA_ENTRE_INTENTOS_MS) {
            const espera = Math.min(
                PAUSA_ENTRE_INTENTOS_MS - consumido,
                Math.max(0, finDeVentana - Date.now()),
            );
            if (espera > 0) {
                await new Promise((listo) => {
                    setTimeout(listo, espera);
                });
            }
        }
    }

    /* eslint-enable no-await-in-loop */

    // La ventana se agotó. La razón distingue dos hechos que no son el mismo:
    // no haber conseguido ningún punto, y haberlos conseguido todos
    // demasiado imprecisos. Decir lo segundo con la razón del primero sería
    // sobrecargar un motivo con un hecho que no describe (§29).
    await declararMissing(
        eventKind,
        subject,
        huboCandidato && mejorPrecisionRechazada !== null
            ? 'recovery_accuracy_rejected'
            : razonDe(ultimoFallo?.code),
        intentos,
        permiso,
        mejorPrecisionRechazada !== null
            ? { ...(rechazado ?? {}), accuracy_m: mejorPrecisionRechazada }
            : rechazado,
    );
}

/** Evita capturar dos veces lo mismo si la pantalla despacha la acción dos veces. */
const enCurso = new Set<string>();

/**
 * Intenta situar un evento del ciclo de vida. **No se espera con `await`.**
 *
 * Nunca lanza: un fallo de ubicación no puede propagarse al flujo operativo.
 * Todo lo que sale mal acaba en el servidor como Missing, o en la nada si
 * tampoco se puede llegar al servidor — y en ese caso el barrido del servidor
 * lo cerrará al vencer la ventana, que es el tercer camino de §11.
 */
export function captureFor(eventKind: LocationEventKind, subject: Sujeto): void {
    // La llave del almacén sale de lo que identifique al sujeto. Con la clave
    // de acción es única por acción, así que **dos acciones offline del mismo
    // tipo no colisionan** — que es exactamente lo que el mecanismo anterior no
    // podía garantizar, y por eso se negaba a atar.
    const llave = 'clientActionKey' in subject
        ? `${eventKind}:key:${subject.clientActionKey}`
        : `${eventKind}:${subject.subjectId}`;
    if (enCurso.has(llave)) return;
    enCurso.add(llave);

    (async () => {
        try {
            await capturar(eventKind, subject);
        } catch {
            // Silencio deliberado (§12). Si ni la captura ni el aviso de Missing
            // llegaron, el sweeper del servidor cierra el evento al vencer la
            // ventana: no hace falta que el cliente insista aquí.
        } finally {
            enCurso.delete(llave);
        }
    })().catch(() => {
        // Inalcanzable: el `try` de dentro ya lo cubre. Está porque la regla
        // del proyecto no permite descartar una promesa con `void`.
    });
}
