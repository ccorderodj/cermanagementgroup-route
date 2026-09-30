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
    changeTripPlan,
    fetchPlanChanges,
    queueArrive,
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
import { captureFor } from '@/shared/lib/location';

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
    const ultimaJornada = useRef<WorkSession | null>(null);
    // La última vista que el servidor confirmó. Es a la que se vuelve sin
    // red: ver la parada de hace un minuto es cierto, y ofrecer
    // el workbench con una llegada sin resolver no lo es (FR-01).
    const ultimaVista = useRef<Vista | null>(null);

    const detalleDeError = (err: unknown, porDefecto: string) => {
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
            setOdometro(
                await fetchSessionOdometer(sesion.id).catch(() => null),
            );

            const confirmar = (vista: Vista) => {
                ultimaVista.current = vista;
                setView(vista);
            };

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
    const iniciarJornada = async () => {
        const ok = await ejecutar(queueStartWork, 'Your workday could not be started.');
        if (!ok) return false;
        const actual = await fetchCurrentWorkSession().catch(() => null);
        if (actual?.work_session) captureFor('start_work', actual.work_session.id);
        return true;
    };

    // La evidencia de odómetro, derivada antes que las acciones porque
    // `salirDeViaje` la consulta: sin lectura de inicio resuelta no se crea
    // ningún viaje.
    const inicio: OdometerEvidence | null = odometro?.start ?? null;
    const faltaInicio = inicio !== null && !isOdometerResolved(inicio.status);
    const capturandoOdometro = capturandoInicio && inicio !== null;
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
            await queuePlanTrip(plan);
            await syncPendingWorkSessionActions();

            const tras = await fetchCurrentWorkSession();
            const viaje = tras.current_trip;
            if (viaje && viaje.status === 'planning') {
                await queueStartTrip(viaje.id);
                await syncPendingWorkSessionActions();
                // El primer waypoint del kilometraje (§18). Sin `await`.
                captureFor('start_trip', viaje.id);
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
        if (ok) captureFor('start_trip', trip.id);
        return ok;
    };

    const llegar = async (trip: Trip) => {
        const ok = await ejecutar(() => queueArrive(trip.id), 'Your arrival could not be recorded.');
        // El waypoint final (§18). Si la llegada se encoló sin red, el punto no
        // podrá atarse todavía y lo cerrará el barrido del servidor: la captura
        // no puede retrasar la pantalla para esperarlo.
        if (ok) captureFor('arrived', trip.id);
        return ok;
    };

    const cambiarPlan = async (trip: Trip, plan: TripPlanInput) => {
        const ok = await ejecutar(() => changeTripPlan(trip.id, plan), 'The plan could not be changed.');
        if (ok) {
            // Cada Change Plan es un waypoint autoritativo (§16), y su sujeto es
            // la **fila del cambio**, no el viaje: así varios cambios del mismo
            // viaje quedan independientes y ordenados. `change-plan` devuelve el
            // viaje, no el cambio, así que el id se lee del historial.
            fetchPlanChanges(trip.id)
                .then((cambios) => {
                    const ultimo = cambios.at(-1);
                    if (ultimo) captureFor('change_plan', ultimo.id);
                })
                .catch(() => {
                    // Silencio (§12). Sin el id no se puede atar el punto, y el
                    // barrido del servidor cerrará el evento al vencer la ventana.
                });
        }
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
            captureFor('end_work', session.id);
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

            const cierre = await fetchSessionOdometer(session.id).catch(() => null);
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
        setCapturandoInicio(false);

        if (pendiente) {
            setPlanPendiente(null);
            await salirDeViaje(pendiente, true);
        }
    };

    /** Cancelar la captura devuelve al workbench, sin viaje empezado. */
    const cancelarOdometro = () => {
        setCapturandoInicio(false);
        setPlanPendiente(null);
    };

    return (
        <RouteMobileShell title="My Route" active="my-route">
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
                        {faltaInicio && !capturandoInicio && preparando === null && inicio && (
                            <OdometerPendingBanner
                                status={inicio.status}
                                disabled={busy}
                                onCapture={() => setCapturandoInicio(true)}
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
                        {!capturandoOdometro && preparando !== null && (
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
                                    aparece sin más. */}
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
                                {/* Secundario a propósito: terminar el día no
                                    compite con empezar la siguiente tarea, pero
                                    tiene que estar — hay jornadas sin un solo
                                    viaje y no se fabrica un viaje a casa falso
                                    para poder cerrarlas (PD-02, A-1). */}
                                <Button
                                    variant="ghost"
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

                        {faltaInicio && inicio ? (
                            <OdometerCapture
                                sessionId={view.session.id}
                                end="start"
                                evidence={inicio}
                                onResolved={odometroResuelto}
                                onChanged={reconcile}
                            />
                        ) : (
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
                                <Button
                                    variant="outline"
                                    size="lg"
                                    className="h-14 w-full"
                                    disabled={busy}
                                    onClick={() => setCambiandoPlan(true)}
                                >
                                    Change Plan
                                </Button>
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
                                    // Pedida la excepción, el día ya puede
                                    // cerrarse: la evidencia queda pendiente y
                                    // `ended_at` se escribe a su hora real.
                                    await cerrarJornada(view.session, true);
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
