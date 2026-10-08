import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/shared/ui/shadcn/new-york';
import { ConfirmDestructiveDialog } from '@/features/Common';
import { RouteMobileShell } from '@/widgets/RouteShell';
import { TripContextChoices, TripContextForm, TripContextPicker } from '@/features/RouteTrip';
import { ActivityStop } from '@/features/RouteActivity';
import type { ActivityExecution } from '@/entities/RouteActivities';
import {
    OdometerCapture,
    OdometerDistance,
    OdometerPendingBanner,
} from '@/features/RouteOdometer';
import {
    fetchSessionOdometer,
    isOdometerResolved,
    readingAsNumber,
    type OdometerEvidence,
    type OdometerSessionState,
} from '@/entities/RouteOdometer';
import {
    queueArrive,
    queueChangePlan,
    queuePlanTrip,
    queueStartTrip,
    TRIP_CONTEXTS,
    type Trip,
    type TripPlanInput,
    type TripPurpose,
} from '@/entities/RouteTrips';
import {
    fetchCurrentWorkSession,
    queueEndWork,
    queueStartWork,
    syncPendingWorkSessionActions,
    type WorkSession,
} from '@/entities/RouteWorkSessions';
import { listPendingActions } from '@/shared/lib/offlineQueue';
import {
    captureFor, PermisoDeUbicacionRequerido, type PermisoOperativo,
} from '@/shared/lib/location';
import { LocationGate } from '@/features/RouteLocationGate';

/**
 * La jornada del supervisor, de principio a fin.
 *
 * Una sola acción principal a la vez, sin cromo de administración y sin
 * vocabulario de máquina de estados: el supervisor lee "On route", no
 * `IN_TRANSIT`. Escribe lo mínimo, porque puede estar a punto de conducir.
 *
 * El workbench
 * ------------
 * `What's next?` es el estado de reposo de una jornada activa: se llega a él al
 * empezar el día y se vuelve a él al cerrar cada parada. No hay una pantalla
 * intermedia que anuncie que la jornada está abierta y ofrezca un botón para
 * ver las opciones — eso era una pulsación que no añadía información.
 *
 * Es también el **único** sitio desde el que se termina el día. Preparar un
 * viaje, conducir y ejecutar una parada no ofrecen esa salida: no porque el
 * servidor no sepa rechazarla —sabe—, sino porque una salida a mitad de una
 * decisión a medio tomar es ambigua para quien la pulsa.
 *
 * El servidor es la única autoridad
 * ----------------------------------
 * Cada reapertura, reconexión o reautenticación arranca de
 * `GET /worksessions/current`, que devuelve la jornada y su viaje vivo. Esta
 * pantalla no se fía de lo que tenga guardado: si el servidor dice otra cosa,
 * gana el servidor. Un segundo dispositivo resuelve el mismo viaje en vez de
 * crear otro.
 *
 * Y cuando el servidor rechaza algo, la pantalla **vuelve a preguntarle en qué
 * estado está** en vez de leer el texto del error. Un 409 al cerrar la jornada
 * puede ser un viaje sin terminar o una lectura de odómetro sin hacer, y
 * distinguirlos comparando cadenas rompería el día que alguien mejore una
 * frase.
 *
 * Al llegar
 * ---------
 * Un viaje operativo que llegó abre la parada (RTE05): se elige qué se hace
 * donde el contexto lo pide, y se sale terminando o marchándose —las dos
 * diciendo cómo fue—. Nada cierra el viaje por su cuenta: `End Work` con una
 * parada sin resolver recibe un 409 y lo dice, no cierra el día por detrás.
 *
 * `HOME` no pasa por aquí: su viaje se cierra al llegar, porque volver a casa
 * no es una parada de trabajo.
 */

function formatearHora(iso: string): string {
    return new Date(iso).toLocaleTimeString(undefined, {
        hour: 'numeric',
        minute: '2-digit',
    });
}

type Vista =
    | { phase: 'loading' }
    | { phase: 'no-session' }
    | { phase: 'start-queued' }
    | { phase: 'working'; session: WorkSession }
    | { phase: 'planning'; session: WorkSession; trip: Trip }
    | { phase: 'on-route'; session: WorkSession; trip: Trip }
    | {
        phase: 'arrived';
        session: WorkSession;
        trip: Trip;
        /** El bloque de la parada, si ya se arrancó. */
        execution: ActivityExecution | null;
    }
    | { phase: 'ending'; session: WorkSession }
    | { phase: 'end-queued'; session: WorkSession }
    | { phase: 'error' };

/**
 * Definidos fuera del render a propósito: declararlos dentro haría que React
 * viera un tipo de componente nuevo en cada render y destruyera su subárbol
 * —y su estado— cada vez.
 */
function Cabecera({ session }: { session: WorkSession }) {
    return (
        <section className="rounded-lg border border-border bg-card p-5 text-center">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
                Working since
            </p>
            <p className="mt-1 text-2xl font-semibold text-foreground">
                {formatearHora(session.started_at)}
            </p>
        </section>
    );
}

function Destino({ trip }: { trip: Trip }) {
    const contexto = TRIP_CONTEXTS[trip.current_purpose];
    const cambiado = trip.current_purpose !== trip.original_purpose;
    return (
        <section className="rounded-lg border border-border bg-card p-5 text-center">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
                {trip.status === 'arrived' ? 'Arrived at' : 'Heading to'}
            </p>
            <p className="mt-1 text-xl font-semibold text-foreground">
                {contexto.label}
            </p>
            {trip.current_context_reference && (
                <p className="mt-1 text-sm text-muted-foreground">
                    {trip.current_context_reference}
                </p>
            )}
            {cambiado && (
                <p className="mt-2 text-xs text-muted-foreground">
                    Originally:
                    {' '}
                    {TRIP_CONTEXTS[trip.original_purpose].label}
                </p>
            )}
        </section>
    );
}

/**
 * La tarea de odómetro que el supervisor tenía abierta, de forma que
 * sobreviva a que Android recree la pestaña al volver de la cámara.
 *
 * Por qué hace falta algo durable
 * -------------------------------
 * `capturandoInicio` es `useState`. Mientras el proceso de la página viva da
 * igual, pero Android Chrome descarta y recrea la pestaña con frecuencia al
 * abrir la cámara bajo presión de memoria, y entonces todo el estado de React
 * se pierde: la página vuelve al workbench con la tarea sin resolver y nada
 * que indique dónde estaba el supervisor. Es el hallazgo de campo.
 *
 * Por qué `sessionStorage` y no el servidor
 * -----------------------------------------
 * Esto **no es evidencia**: es dónde estaba mirando una persona. Mandarlo al
 * servidor crearía estado de interfaz en el dominio, que es justo lo que la
 * arquitectura evita. `sessionStorage` dura lo que la pestaña, que es
 * exactamente lo que tiene que durar.
 *
 * Y no sustituye a la verdad de dominio: si hay foto subida, la tarea se
 * reanuda igual aunque esto esté vacío —ver `capturandoOdometro`—. Esto sólo
 * cubre el caso en el que la página murió **antes** de que la foto llegara a
 * subirse, que no deja ningún rastro en el servidor (ODO-05).
 */
function llaveDeTarea(sessionId: number, end: 'start' | 'end'): string {
    return `cer.route.odometer.${sessionId}.${end}`;
}

function marcarTarea(sessionId: number, end: 'start' | 'end'): void {
    try {
        sessionStorage.setItem(llaveDeTarea(sessionId, end), '1');
    } catch {
        // Modo privado o almacenamiento bloqueado. No es un fallo: se pierde
        // la reanudación en ese caso concreto y el resto sigue igual.
    }
}

function olvidarTarea(sessionId: number, end: 'start' | 'end'): void {
    try {
        sessionStorage.removeItem(llaveDeTarea(sessionId, end));
    } catch {
        // Ídem.
    }
}

function tareaMarcada(sessionId: number, end: 'start' | 'end'): boolean {
    try {
        return sessionStorage.getItem(llaveDeTarea(sessionId, end)) === '1';
    } catch {
        return false;
    }
}

/** Si la evidencia ya tiene foto subida. Verdad de dominio, no de interfaz. */
function tieneFotoPersistida(evidencia: OdometerEvidence | null): boolean {
    return evidencia !== null
        && evidencia.captured_at !== null
        && evidencia.captured_at !== undefined;
}

/**
 * Cuántas veces se reintenta leer la evidencia antes de darla por ilegible.
 *
 * El fallo que esto cubre es el parpadeo de las primeras peticiones cuando
 * Android acaba de recrear la pestaña: se resuelve muy por debajo del segundo.
 * Tres intentos con pausa creciente cubren algo más de un segundo, que es
 * suficiente para ese caso y poco para que la pantalla parezca colgada. No es
 * un mecanismo de reintento general: si el servidor está caído, se agota y se
 * dice.
 */
const INTENTOS_DE_LECTURA = 3;
const PAUSA_DE_LECTURA_MS = 400;

/**
 * La evidencia de odómetro de la jornada. **Lanza si no se pudo leer.**
 *
 * Que lance es el punto de esta función. Antes la lectura era
 * `fetchSessionOdometer(...).catch(() => null)`, y ese `null` significaba a la
 * vez "no hay evidencia" y "no pude preguntar". La pantalla decide con eso si
 * hay una lectura de cierre pendiente, así que un fallo de red momentáneo
 * acababa afirmando que no había nada pendiente — y devolvía al supervisor al
 * workbench con la tarea viva en el servidor.
 *
 * Separarlas es todo el arreglo: aquí se devuelve lo que el servidor dijo, o se
 * lanza. Quien llama decide qué hacer con la incertidumbre, y lo que no puede
 * hacer es confundirla con una respuesta.
 */
async function leerOdometro(sessionId: number): Promise<OdometerSessionState> {
    let ultimoFallo: unknown;

    // Secuencial a propósito: cada intento tiene que terminar antes de decidir
    // si merece la pena otro.
    /* eslint-disable no-await-in-loop */
    for (let intento = 0; intento < INTENTOS_DE_LECTURA; intento += 1) {
        try {
            return await fetchSessionOdometer(sessionId);
        } catch (err) {
            ultimoFallo = err;
            if (intento + 1 < INTENTOS_DE_LECTURA) {
                await new Promise((listo) => {
                    setTimeout(listo, PAUSA_DE_LECTURA_MS * (intento + 1));
                });
            }
        }
    }
    /* eslint-enable no-await-in-loop */

    throw ultimoFallo;
}

export const RouteMyRoutePage = () => {
    const [view, setView] = useState<Vista>({ phase: 'loading' });
    const [odometro, setOdometro] = useState<OdometerSessionState | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    // El contexto elegido en el workbench, mientras se rellenan sus datos.
    // Vive en el cliente y no en el servidor **a propósito**: hasta que no se
    // pulsa `Start Trip` no existe ningún viaje, así que volver atrás no deja
    // un viaje fantasma ni escribe historia falsa (FR-04).
    const [preparando, setPreparando] = useState<TripPurpose | null>(null);
    const [cambiandoPlan, setCambiandoPlan] = useState(false);
    // El plan elegido que espera a que se resuelva la lectura de inicio.
    const [planPendiente, setPlanPendiente] = useState<TripPlanInput | null>(null);
    // El odómetro de inicio, abierto desde el aviso antes de elegir destino.
    const [capturandoInicio, setCapturandoInicio] = useState(false);
    // La revisión de End Work con un viaje en ruta (D-07).
    const [revisandoCierre, setRevisandoCierre] = useState(false);
    // Lo que la puerta de ubicación sabe del permiso. `null` mientras no ha
    // contestado: entonces no se retira nada, y la guarda de la cola sigue
    // siendo la que impide abrir trabajo sin acceso.
    const [permisoUbicacion, setPermisoUbicacion] = useState<PermisoOperativo | null>(null);
    const ultimaJornada = useRef<WorkSession | null>(null);
    // La última vista que el servidor confirmó. Es a la que se vuelve sin
    // red: ver la parada de hace un minuto es cierto, y ofrecer
    // el workbench con una llegada sin resolver no lo es (FR-01).
    const ultimaVista = useRef<Vista | null>(null);

    const detalleDeError = (err: unknown, porDefecto: string) => {
        // El permiso de ubicación revocado no es un fallo de red ni un rechazo
        // del servidor: la acción no llegó a encolarse. Sin esta rama diría
        // «no se pudo empezar el viaje», que manda a buscar el problema donde
        // no está.
        if (err instanceof PermisoDeUbicacionRequerido) return err.message;
        const detalle = (err as { response?: { data?: { detail?: string } } })
            ?.response?.data?.detail;
        return detalle ?? porDefecto;
    };

    /** Reconcilia contra el servidor. Es el único camino a un estado nuevo. */
    const reconcile = useCallback(async () => {
        try {
            await syncPendingWorkSessionActions();
        } catch {
            // Sin red no se sincroniza; se sigue para leer lo que haya.
        }

        try {
            const actual = await fetchCurrentWorkSession();
            const sesion = actual.work_session;
            const viaje = actual.current_trip ?? null;

            if (!sesion) {
                ultimaJornada.current = null;
                ultimaVista.current = null;
                setOdometro(null);
                setView({ phase: 'no-session' });
                return;
            }

            ultimaJornada.current = sesion;

            // La evidencia de odómetro se lee junto a la jornada: de ella
            // depende si se puede salir, y no tenerla a mano obligaría a la
            // pantalla a adivinar.
            //
            // Si no se puede leer, **no se decide ninguna fase con eso**. No
            // saber si hay lectura de cierre pendiente no es lo mismo que saber
            // que no la hay, y confundirlos es el defecto que CER reprodujo en
            // campo: aquí había un `.catch(() => null)`, un fallo de lectura
            // caía en la misma rama que "no hay evidencia", y el supervisor
            // acababa en el workbench con su lectura de cierre viva en el
            // servidor y nada que lo dijera.
            let evidencia: OdometerSessionState;
            try {
                evidencia = await leerOdometro(sesion.id);
            } catch {
                if (ultimaVista.current) {
                    // Se queda donde estaba. Si estaba en la pantalla de
                    // cierre, sigue en ella: no se le mueve por no haber
                    // podido preguntar.
                    setView(ultimaVista.current);
                } else {
                    // Arranque en frío —la pestaña se acaba de recrear— y
                    // tampoco se pudo leer. Se dice que no se pudo cargar, que
                    // es verdad, en vez de enseñar un workbench que afirmaría
                    // en silencio que no queda nada pendiente.
                    setView({ phase: 'error' });
                }
                return;
            }
            setOdometro(evidencia);

            const confirmar = (vista: Vista) => {
                ultimaVista.current = vista;
                setView(vista);
            };

            // La lectura de CIERRE pendiente manda sobre cualquier otra fase.
            //
            // Antes, `phase: 'ending'` sólo se ponía dentro del flujo de cerrar
            // la jornada, así que era estado volátil: si Android recreaba la
            // pestaña al volver de la cámara, `reconcile` calculaba `working` y
            // la tarea de cierre desaparecía de la vista, con la evidencia
            // pendiente en el servidor y nada que lo dijera. Era el hallazgo de
            // campo en su mitad de END (ODO-03).
            //
            // Ahora sale de la evidencia, que es verdad de dominio y sobrevive
            // a todo. Y **no reabre la jornada**: `ended_at` ya está escrito, y
            // esto sólo decide qué pantalla se muestra.
            if (evidencia?.end && !isOdometerResolved(evidencia.end.status)) {
                confirmar({ phase: 'ending', session: sesion });
                return;
            }

            if (!viaje) {
                confirmar({ phase: 'working', session: sesion });
                return;
            }
            if (viaje.status === 'planning') {
                confirmar({ phase: 'planning', session: sesion, trip: viaje });
                return;
            }
            if (viaje.status === 'in_transit') {
                confirmar({ phase: 'on-route', session: sesion, trip: viaje });
                return;
            }
            // El bloque viene en la misma respuesta que la jornada: la
            // pantalla no tiene que deducir a dónde volver cruzando
            // propósito, estado del viaje y estado de la parada.
            confirmar({
                phase: 'arrived',
                session: sesion,
                trip: viaje,
                execution: actual.current_activity ?? null,
            });
        } catch {
            // Sin servidor se infiere de lo pendiente, sin inventar un viaje:
            // lo único que se puede afirmar sin red es que hay algo encolado.
            const pendientes = await listPendingActions().catch(() => []);
            if (pendientes.some((a) => a.kind === 'worksession.start')) {
                setView({ phase: 'start-queued' });
            } else if (ultimaVista.current) {
                // Lo último que el servidor dijo, no un estado más simple:
                // colapsar al workbench con un viaje sin resolver
                // ofrecía planificar un segundo viaje que el servidor va a
                // rechazar —hay un único viaje vivo por jornada— y escondía
                // el trabajo que quedaba en la parada.
                setView(ultimaVista.current);
            } else if (ultimaJornada.current) {
                setView({ phase: 'working', session: ultimaJornada.current });
            } else {
                setView({ phase: 'error' });
            }
        }
    }, []);

    useEffect(() => {
        reconcile();
        const alVolver = () => {
            if (document.visibilityState === 'visible') reconcile();
        };
        document.addEventListener('visibilitychange', alVolver);
        window.addEventListener('online', reconcile);
        return () => {
            document.removeEventListener('visibilitychange', alVolver);
            window.removeEventListener('online', reconcile);
        };
    }, [reconcile]);

    const ejecutar = async (accion: () => Promise<unknown>, mensaje: string) => {
        setBusy(true);
        setError(null);
        try {
            await accion();
            await reconcile();
            return true;
        } catch (err) {
            setError(detalleDeError(err, mensaje));
            await reconcile();
            return false;
        } finally {
            setBusy(false);
        }
    };

    /**
     * Empezar el día, y situarlo sin que se note.
     *
     * La captura va **después** de reconciliar porque el id de la jornada sale
     * de ahí, y se lanza sin `await`: §11 y §36 prohíben que la acción espere a
     * la ubicación. Si el GPS tarda quince segundos, el supervisor ya está en
     * el workbench.
     */
    /**
     * Empezar el día, y situarlo sin que se note.
     *
     * El punto se identifica por la **clave de la acción**, con red o sin ella.
     * Da igual que la jornada llegue a existir en el servidor durante esta
     * pulsación o al reconectar dentro de una hora: la clave es la misma, el
     * servidor la guarda en la fila al crearla, y el punto se ata a **esa**
     * jornada y no a la que hubiera.
     *
     * Antes había dos caminos —id si confirmaba, sujeto diferido si no— y el
     * segundo se negaba a atar cuando había dos acciones del mismo tipo
     * pendientes. Un solo camino y ninguna deducción.
     */
    const iniciarJornada = async () => {
        const accion = await queueStartWork();
        captureFor('start_work', { clientActionKey: accion.id });
        return ejecutar(
            async () => accion,
            'Your workday could not be started.',
        );
    };

    // La evidencia de odómetro, derivada antes que las acciones porque
    // `salirDeViaje` la consulta: sin lectura de inicio resuelta no se crea
    // ningún viaje.
    const inicio: OdometerEvidence | null = odometro?.start ?? null;
    const faltaInicio = inicio !== null && !isOdometerResolved(inicio.status);
    // La captura de inicio se abre por tres caminos, y los tres son
    // restaurables. El primero es el único volátil, y a propósito: los otros
    // dos son los que hacen que la tarea sobreviva a que Android recree la
    // pestaña al volver de la cámara (ODO-01, ODO-02, ODO-05).
    //
    //   1. el supervisor acaba de pulsar el botón;
    //   2. **ya hay foto subida** — verdad de dominio: la tarea está a medias
    //      y lo que falta es confirmar la lectura (ODO-04);
    //   3. quedó marcada la intención antes de abrir la cámara, para el caso
    //      en que la página muriera **antes** de subir la foto (ODO-05).
    const capturandoOdometro = inicio !== null && faltaInicio && (
        capturandoInicio
        || tieneFotoPersistida(inicio)
        || tareaMarcada(ultimaJornada.current?.id ?? -1, 'start')
    );
    const distancia = readingAsNumber(odometro?.odometer_distance);

    /**
     * Preparar y salir, en una sola pulsación.
     *
     * El dominio sigue teniendo sus dos pasos —`PLANNING` y luego
     * `IN_TRANSIT`— porque son estados certificados de RTE04 y no se tocan. Lo
     * que desaparece es la pantalla intermedia: para el supervisor, elegir a
     * dónde va y salir es una sola decisión (PD-05).
     *
     * El viaje **no se crea hasta aquí**. Mientras se rellena el formulario no
     * hay nada escrito, así que volver atrás no deja un viaje fantasma.
     *
     * Si la lectura de odómetro está pendiente, se para antes de crear nada y
     * se pide: así un bloqueo previsible no deja un `PLANNING` colgado que
     * después nadie sabría cerrar.
     */
    const salirDeViaje = async (plan: TripPlanInput, yaCapturado = false) => {
        // `yaCapturado` existe porque el estado de React no se ha actualizado
        // todavía cuando se vuelve de resolver la lectura: leer `faltaInicio`
        // aquí devolvería el valor viejo y mandaría a capturar otra vez, en
        // bucle. Quien acaba de resolverla lo sabe y lo dice.
        if (!yaCapturado && faltaInicio) {
            setPreparando(null);
            // Se marca aquí por lo mismo que en el aviso del workbench: desde
            // este punto hay una tarea de lectura abierta, y si Android recrea
            // la pestaña con la cámara delante esto es lo único que queda para
            // saberlo.
            //
            // Faltaba. La marca sólo se ponía al entrar por el aviso, así que
            // quien llegaba a la captura pulsando `Start Trip` —que es el
            // camino normal— perdía la tarea si la página moría antes de subir
            // la foto. Era el mismo hallazgo de campo por la otra puerta.
            marcarTarea(ultimaJornada.current?.id ?? -1, 'start');
            setCapturandoInicio(true);
            setPlanPendiente(plan);
            return;
        }

        setBusy(true);
        setError(null);
        try {
            // Encolar no es enviar: la cola guarda la acción y la envía al
            // vaciarse. Sin vaciarla aquí, el servidor todavía no tendría el
            // viaje y no habría identificador con el que arrancarlo.
            const accionDelPlan = await queuePlanTrip(plan);
            // El waypoint de salida se identifica por la clave de **la acción
            // que crea el viaje**, no por su id: sin red el id no existe, y con
            // red la clave sigue siendo igual de válida. Se captura antes de
            // enviar, así que una caída de red entre medias no pierde el punto.
            captureFor('start_trip', { clientActionKey: accionDelPlan.id });
            await syncPendingWorkSessionActions();

            const tras = await fetchCurrentWorkSession();
            const viaje = tras.current_trip;
            if (viaje && viaje.status === 'planning') {
                await queueStartTrip(viaje.id);
                await syncPendingWorkSessionActions();
            }
            // Sin red no hay viaje que arrancar todavía: el plan se queda en la
            // cola y se reanudará al reconectar, que es para lo que existe.
            setPreparando(null);
            setPlanPendiente(null);
            await reconcile();
        } catch (err) {
            setError(detalleDeError(err, 'This trip could not be started.'));
            await reconcile();
        } finally {
            setBusy(false);
        }
    };

    /** Reanudar un viaje que quedó preparado y sin salir (cola sin red). */
    const arrancarViaje = async (trip: Trip) => {
        const ok = await ejecutar(() => queueStartTrip(trip.id), 'This trip could not be started.');
        // Aquí el viaje **ya existe** en el servidor —se está reanudando uno que
        // quedó preparado— así que su id es el identificador correcto.
        if (ok) captureFor('start_trip', { subjectId: trip.id });
        return ok;
    };

    const llegar = async (trip: Trip) => {
        const ok = await ejecutar(() => queueArrive(trip.id), 'Your arrival could not be recorded.');
        // El waypoint final (§18). Si la llegada se encoló sin red, el punto no
        // podrá atarse todavía y lo cerrará el barrido del servidor: la captura
        // no puede retrasar la pantalla para esperarlo.
        if (ok) captureFor('arrived', { subjectId: trip.id });
        return ok;
    };

    const cambiarPlan = async (trip: Trip, plan: TripPlanInput) => {
        // Change Plan pasa por la cola desde el cierre final de RTE06. Era la
        // única acción del ciclo de vida que se llamaba directamente, y eso
        // impedía las dos cosas que el cierre exige: que sobreviva a un corte de
        // red, y que su punto se ate a **ese** cambio y no a otro del mismo
        // viaje. Ya no hace falta leer el historial para saber a qué atarlo: la
        // clave de la acción lo identifica.
        const accion = await queueChangePlan(trip.id, plan);
        captureFor('change_plan', { clientActionKey: accion.id });
        const ok = await ejecutar(async () => accion, 'The plan could not be changed.');
        if (ok) setCambiandoPlan(false);
    };

    /**
     * Cerrar la jornada.
     *
     * `End Work` pasa por la cola durable, así que su resultado real llega en
     * el `FlushResult`: un rechazo del servidor sale de la cola —no se
     * reintentará solo y no cerrará el día por su cuenta— y vuelve aquí. Con un
     * 409 la pantalla **relee el estado** y decide por él: viaje sin terminar
     * abre la revisión de D-07; lectura de cierre pendiente abre la captura.
     */
    const cerrarJornada = async (session: WorkSession, deTodosModos = false) => {
        setBusy(true);
        setError(null);
        try {
            // La recuperación de End Work puede terminar después de que la
            // jornada esté ENDED: es la excepción acotada de §13, y el servidor
            // la admite sólo para este evento y dentro de la ventana. Se lanza
            // **antes** del envío para que la ventana empiece a contar ya.
            captureFor('end_work', { subjectId: session.id });
            await queueEndWork(session.id, deTodosModos);
            const resultado = await syncPendingWorkSessionActions();
            const rechazo = resultado.rejected?.kind === 'worksession.end'
                ? resultado.rejectedError
                : null;

            if (!rechazo) {
                setRevisandoCierre(false);
                setView({ phase: 'end-queued', session });
                await reconcile();
                return;
            }

            const estado = (rechazo as { response?: { status?: number } })
                ?.response?.status;
            if (estado !== 409) {
                setError(detalleDeError(rechazo, 'Your workday could not be ended.'));
                await reconcile();
                return;
            }

            // 409: el servidor dice que falta algo. Cuál, lo dice su estado.
            const actual = await fetchCurrentWorkSession().catch(() => null);
            const viaje = actual?.current_trip ?? null;
            if (viaje?.status === 'in_transit' && !deTodosModos) {
                setRevisandoCierre(true);
                await reconcile();
                return;
            }

            // Parada sin resolver: no hay nada que confirmar ni que forzar.
            // Terminar o marcharse es una decisión con resultado, así que la
            // pantalla vuelve a la parada en vez de ofrecer un atajo que el
            // servidor va a rechazar igual —`end_anyway` cubre el viaje en
            // ruta de D-07, no esto.
            if (actual?.post_arrival_pending) {
                setRevisandoCierre(false);
                setError('Finish or leave this stop before ending your workday.');
                await reconcile();
                return;
            }

            // Con reintento, por lo mismo que en `reconcile`: un parpadeo de
            // red aquí le enseñaría al supervisor el rechazo del servidor en
            // vez de la lectura que tiene que resolver. Si aun así no se puede
            // leer, el `reconcile()` de abajo es la red: ya no colapsa al
            // workbench cuando no sabe.
            const cierre = await leerOdometro(session.id).catch(() => null);
            setOdometro(cierre);
            if (cierre?.end && !isOdometerResolved(cierre.end.status)) {
                setRevisandoCierre(false);
                setView({ phase: 'ending', session });
                return;
            }

            setError(detalleDeError(rechazo, 'Your workday could not be ended.'));
            await reconcile();
        } catch (err) {
            setError(detalleDeError(err, 'Your workday could not be ended.'));
            await reconcile();
        } finally {
            setBusy(false);
        }
    };

    const planDe = (trip: Trip): TripPlanInput => ({
        purpose: trip.current_purpose,
        context_reference: trip.current_context_reference ?? null,
        standard_value_id: trip.current_standard_value_id ?? null,
    });

    /** Vuelve al flujo que estaba en marcha, sin volver a elegir destino. */
    /**
     * Resuelta la lectura, se retoma lo que el supervisor estaba haciendo.
     *
     * Si había elegido un destino y el odómetro le interrumpió, el viaje sale
     * ahora sin pedirle que vuelva a elegirlo: la interrupción fue nuestra, no
     * suya.
     */
    const odometroResuelto = async () => {
        const pendiente = planPendiente;

        // Se reconcilia **antes** de cerrar la captura, y el orden importa: al
        // revés, el workbench aparecía con la evidencia todavía sin refrescar y
        // la primera pulsación de `Start Trip` devolvía a la lectura que acababa
        // de resolverse. Mientras se consulta, el supervisor sigue viendo la
        // captura — que es la verdad: aún no sabemos que quedó resuelta.
        await reconcile();
        // La tarea quedó resuelta: la marca ya no describe nada y dejarla
        // reabriría la captura en el siguiente arranque de la pestaña.
        olvidarTarea(ultimaJornada.current?.id ?? -1, 'start');
        setCapturandoInicio(false);

        if (pendiente) {
            setPlanPendiente(null);
            await salirDeViaje(pendiente, true);
        }
    };

    /** Cancelar la captura devuelve al workbench, sin viaje empezado. */
    const cancelarOdometro = () => {
        // Cancelar es una decisión del supervisor, así que la marca se va con
        // ella: reanudar algo que alguien acaba de cerrar sería ignorarle.
        olvidarTarea(ultimaJornada.current?.id ?? -1, 'start');
        setCapturandoInicio(false);
        setPlanPendiente(null);
    };

    // Hay jornada abierta -> el gate deja pasar, para que se pueda CERRAR lo
    // que esté abierto (§8). Lo que bloquea entonces no es la pantalla sino la
    // guarda por acción de `enqueueAction`: se puede llegar, completar y
    // terminar el día; no se puede empezar nada nuevo.
    //
    // Sin jornada abierta no hay nada que cerrar, así que la puerta es total.
    const hayOperacionAbierta = !['loading', 'error', 'no-session'].includes(view.phase);
    // Sin acceso a la ubicacion y con algo abierto, la pantalla solo ofrece
    // CERRAR (§8). Lo que abre trabajo nuevo desaparece: un boton que existe y
    // falla al pulsarlo es exactamente el estado "normal y accionable" que §5.1
    // prohibe, y es lo que se vio en campo con la primera version de la puerta.
    const soloCierre = permisoUbicacion !== null
        && permisoUbicacion !== 'granted'
        && hayOperacionAbierta;

    return (
        <RouteMobileShell title="My Route" active="my-route">
            <LocationGate
                hayOperacionAbierta={hayOperacionAbierta}
                onPermisoChange={setPermisoUbicacion}
            >
                <div data-testid="RouteMyRoutePage" className="flex flex-col gap-4">
                    {view.phase === 'loading' && (
                        <p className="py-12 text-center text-sm text-muted-foreground">
                            Loading…
                        </p>
                    )}

                    {view.phase === 'error' && (
                        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-center">
                            <p className="text-sm text-destructive">
                                Your workday could not be loaded. Check your connection.
                            </p>
                            <Button variant="outline" className="mt-3" onClick={() => reconcile()}>
                                Try again
                            </Button>
                        </div>
                    )}

                    {error && view.phase !== 'error' && (
                        <p className="rounded-md bg-destructive/10 p-3 text-center text-sm text-destructive">
                            {error}
                        </p>
                    )}

                    {view.phase === 'no-session' && (
                        <div className="flex flex-col items-center gap-6 py-16">
                            <p className="text-center text-sm text-muted-foreground">
                                Ready to start your day?
                            </p>
                            <Button
                                size="lg"
                                className="h-16 w-full max-w-xs text-lg"
                                disabled={busy}
                                onClick={iniciarJornada}
                            >
                                Start Work
                            </Button>
                        </div>
                    )}

                    {view.phase === 'start-queued' && (
                        <div className="flex flex-col items-center gap-3 py-16">
                            <p className="text-center text-base font-medium text-foreground">
                                Starting your day…
                            </p>
                            <p className="text-center text-sm text-muted-foreground">
                                This will sync as soon as you have a connection.
                            </p>
                        </div>
                    )}

                    {view.phase === 'working' && (
                        <div className="flex flex-col gap-6">
                            <Cabecera session={view.session} />

                            {/* El aviso, no un diálogo forzado: `Start Work` no es
                            `Start Driving`, y quien empieza el día con trabajo
                            de oficina no tiene por qué fotografiar nada. */}
                            {!soloCierre && faltaInicio && !capturandoInicio && preparando === null && inicio && (
                                <OdometerPendingBanner
                                    status={inicio.status}
                                    disabled={busy}
                                    onCapture={() => {
                                    // Se marca ANTES de que el componente abra
                                    // la cámara: si la página muere con ella
                                    // abierta, esto es lo único que queda.
                                    //
                                    // La llave sale de `ultimaJornada`, que es
                                    // de donde la lee `capturandoOdometro`.
                                    // Escribirla con `view.session.id` —que es
                                    // lo que había— dependía de que los dos
                                    // valores coincidieran siempre; el día que
                                    // no, la marca se guardaba bajo una llave
                                    // que nadie consulta y la tarea se perdía
                                    // sin que nada lo dijera.
                                        marcarTarea(
                                            ultimaJornada.current?.id ?? -1,
                                            'start',
                                        );
                                        setCapturandoInicio(true);
                                    }}
                                />
                            )}

                            {capturandoOdometro && inicio && (
                                <OdometerCapture
                                    sessionId={view.session.id}
                                    end="start"
                                    evidence={inicio}
                                    onResolved={odometroResuelto}
                                    onChanged={reconcile}
                                    onCancel={cancelarOdometro}
                                />
                            )}

                            {/* Elegido el contexto: sus datos y salir, en una
                            pantalla. Sin `End Work` (FR-11): `Back` devuelve al
                            workbench, que es donde se termina el día. */}
                            {!soloCierre && !capturandoOdometro && preparando !== null && (
                                <TripContextForm
                                    purpose={preparando}
                                    busy={busy}
                                    confirmLabel="Start Trip"
                                    onBack={() => setPreparando(null)}
                                    onConfirm={salirDeViaje}
                                />
                            )}

                            {/* El workbench. Las siete opciones **son** la pantalla
                            de reposo: no hay un botón previo que las revele. */}
                            {!capturandoOdometro && preparando === null && (
                                <>
                                    {/* Título y subtítulo literales del mockup
                                    V0.7 aprobado: el workbench se presenta, no
                                    aparece sin más. Sin acceso a la ubicación
                                    no se ofrece: las siete opciones abren un
                                    viaje, y abrir es lo que la puerta impide. */}
                                    {!soloCierre && (
                                        <>
                                            <div>
                                                <p className="text-xl font-bold text-foreground">
                                                    What&apos;s next?
                                                </p>
                                                <p className="mt-0.5 text-xs text-muted-foreground">
                                                    Choose one activity to start a trip.
                                                </p>
                                            </div>
                                            <TripContextChoices
                                                busy={busy}
                                                onSelect={setPreparando}
                                            />
                                        </>
                                    )}
                                    {/* Terminar el día tiene que estar siempre: hay
                                    jornadas sin un solo viaje y no se fabrica un
                                    viaje a casa falso para poder cerrarlas
                                    (PD-02, A-1).
                                    Va en `destructive` por decisión de CER: en
                                    `ghost` se leía como texto y no como botón, y
                                    cerrar la jornada es la acción con más
                                    consecuencias de esta pantalla — con un viaje
                                    sin llegar queda registrado como interrumpido
                                    y no se le inventa una llegada. */}
                                    <Button
                                        variant="destructive"
                                        size="lg"
                                        className="h-12 w-full"
                                        disabled={busy}
                                        onClick={() => cerrarJornada(view.session)}
                                    >
                                        End Work
                                    </Button>
                                </>
                            )}
                        </div>
                    )}

                    {/* Un viaje preparado y sin salir. En el camino normal no
                    aparece —preparar y salir son una sola pulsación—, así que
                    sólo se llega aquí si la salida se interrumpió: sin red, o
                    con la aplicación cerrada en medio. No es una pantalla de
                    confirmación, es reanudar lo que quedó a medias. */}
                    {view.phase === 'planning' && (
                        <div className="flex flex-col gap-6">
                            <Cabecera session={view.session} />
                            <Destino trip={view.trip} />

                            {/* Sin acceso a la ubicación, un viaje preparado y
                            sin salir no está abierto: no hay nada que cerrar en
                            él, y salir sería abrirlo. Tampoco se pide la lectura
                            de inicio, que es el primer paso de salir. La única
                            salida es terminar la jornada, y el servidor la
                            acepta: un viaje en planificación no deja trabajo
                            sin resolver. */}
                            {soloCierre && (
                                <Button
                                    variant="destructive"
                                    size="lg"
                                    className="h-12 w-full"
                                    disabled={busy}
                                    onClick={() => cerrarJornada(view.session)}
                                >
                                    End Work
                                </Button>
                            )}
                            {!soloCierre && faltaInicio && inicio && (
                                <OdometerCapture
                                    sessionId={view.session.id}
                                    end="start"
                                    evidence={inicio}
                                    onResolved={odometroResuelto}
                                    onChanged={reconcile}
                                />
                            )}
                            {!soloCierre && !(faltaInicio && inicio) && (
                                <Button
                                    size="lg"
                                    className="h-16 w-full text-lg"
                                    disabled={busy}
                                    onClick={() => arrancarViaje(view.trip)}
                                >
                                    Start Trip
                                </Button>
                            )}
                        </div>
                    )}

                    {view.phase === 'on-route' && (
                        <div className="flex flex-col gap-6">
                            <Cabecera session={view.session} />
                            <Destino trip={view.trip} />

                            {cambiandoPlan ? (
                                <TripContextPicker
                                    busy={busy}
                                    initial={planDe(view.trip)}
                                    confirmLabel="Update plan"
                                    onCancel={() => setCambiandoPlan(false)}
                                    onConfirm={(plan) => cambiarPlan(view.trip, plan)}
                                />
                            ) : (
                                <>
                                    <Button
                                        size="lg"
                                        className="h-16 w-full text-lg"
                                        disabled={busy}
                                        onClick={() => llegar(view.trip)}
                                    >
                                        {view.trip.current_purpose === 'home'
                                            ? 'Arrived Home'
                                            : 'Arrived'}
                                    </Button>
                                    {/* Cambiar de plan abre un destino nuevo:
                                    sin acceso a la ubicación no se ofrece.
                                    `Arrived`, que cierra el viaje, sí (§8). */}
                                    {!soloCierre && (
                                        <Button
                                            variant="outline"
                                            size="lg"
                                            className="h-14 w-full"
                                            disabled={busy}
                                            onClick={() => setCambiandoPlan(true)}
                                        >
                                            Change Plan
                                        </Button>
                                    )}
                                    {/* Sin `End Work` aquí (PD-03). Conduciendo no
                                    se termina el día: se llega —una llegada que
                                    ocurrió— y se cierra desde el workbench. La
                                    revisión de D-07 sigue existiendo para
                                    cuando el cierre llega por un camino
                                    legítimo, como una acción encolada o un
                                    segundo dispositivo. */}
                                </>
                            )}
                        </div>
                    )}

                    {view.phase === 'arrived' && (
                        <div className="flex flex-col gap-6">
                            <Cabecera session={view.session} />
                            <Destino trip={view.trip} />

                            <ActivityStop
                                trip={view.trip}
                                execution={view.execution}
                                onChanged={reconcile}
                            />

                            {/* Tampoco aquí (PD-03, FR-07). Llegado y sin
                            resolver, lo que hace falta es resolver la parada:
                            terminar o marcharse, las dos con resultado. Cerrado
                            el viaje se vuelve al workbench, y allí sí. */}
                        </div>
                    )}

                    {view.phase === 'ending' && (
                        <div className="flex flex-col gap-6">
                            <Cabecera session={view.session} />
                            <p className="text-center text-sm text-muted-foreground">
                                One last thing before you finish.
                            </p>
                            {odometro?.end && (
                                <OdometerCapture
                                    sessionId={view.session.id}
                                    end="end"
                                    evidence={odometro.end}
                                    onResolved={() => cerrarJornada(view.session, true)}
                                    onChanged={async () => {
                                    /*
                                     * Se **relee la evidencia**, y no se cierra
                                     * el día.
                                     *
                                     * Aquí estaba el defecto que se corrige:
                                     * esto llamaba a `cerrarJornada`, y como
                                     * `Send request` dispara `onChanged`, pedir
                                     * la excepción cerraba la jornada saltándose
                                     * la lectura. El supervisor no llegaba nunca
                                     * al campo manual y `Ending Odometer` se
                                     * quedaba en `Missing`.
                                     *
                                     * Lo que hace falta es justo lo contrario:
                                     * traer el estado nuevo —la excepción queda
                                     * aprobada al enviarse— para que la misma
                                     * pantalla pase a pedirle la lectura. El día
                                     * lo cierra `onResolved`, que sólo se dispara
                                     * cuando la lectura está confirmada.
                                     */
                                        setOdometro(
                                            await leerOdometro(view.session.id),
                                        );
                                    }}
                                />
                            )}
                            <Button
                                variant="ghost"
                                className="h-12 w-full"
                                disabled={busy}
                                onClick={() => reconcile()}
                            >
                                Keep working
                            </Button>
                        </div>
                    )}

                    {view.phase === 'end-queued' && (
                        <div className="flex flex-col gap-3 py-16">
                            <p className="text-center text-sm text-muted-foreground">
                                Ending your day… this will sync as soon as you have a
                                connection.
                            </p>
                            <OdometerDistance distance={distancia} />
                        </div>
                    )}
                </div>
            </LocationGate>

            <ConfirmDestructiveDialog
                open={revisandoCierre}
                onOpenChange={(abierto) => !abierto && setRevisandoCierre(false)}
                title="You are still on route"
                description={(
                    <>
                        This trip has not arrived yet. If you end your workday now,
                        it will be recorded as interrupted — no arrival will be
                        invented for it.
                    </>
                )}
                confirmLabel="End Work Anyway"
                busy={busy}
                onConfirm={() => {
                    const sesion = 'session' in view ? view.session : null;
                    if (sesion) cerrarJornada(sesion, true);
                }}
            />
        </RouteMobileShell>
    );
};

export default RouteMyRoutePage;
