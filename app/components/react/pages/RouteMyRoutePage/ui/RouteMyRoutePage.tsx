import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/shared/ui/shadcn/new-york';
import { ConfirmDestructiveDialog } from '@/features/Common';
import { NotBuiltYet, RouteMobileShell } from '@/widgets/RouteShell';
import { TripContextPicker } from '@/features/RouteTrip';
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
    queueArrive,
    queuePlanTrip,
    queueStartTrip,
    TRIP_CONTEXTS,
    type Trip,
    type TripPlanInput,
} from '@/entities/RouteTrips';
import {
    fetchCurrentWorkSession,
    queueEndWork,
    queueStartWork,
    syncPendingWorkSessionActions,
    type WorkSession,
} from '@/entities/RouteWorkSessions';
import { listPendingActions } from '@/shared/lib/offlineQueue';

/**
 * La jornada del supervisor, de principio a fin.
 *
 * Una sola acción principal a la vez, sin cromo de administración y sin
 * vocabulario de máquina de estados: el supervisor lee "On route", no
 * `IN_TRANSIT`. Escribe lo mínimo, porque puede estar a punto de conducir.
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
 * Lo que no hace, a propósito
 * ----------------------------
 * No cierra un viaje operativo al llegar ni ofrece actividades: eso es RTE05.
 * Un viaje que llegó se queda en `Arrived` y la pantalla dice honestamente que
 * lo siguiente aún no está construido, en vez de enseñar un botón que no hace
 * nada.
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
    | { phase: 'arrived'; session: WorkSession; trip: Trip }
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
    // Elegir contexto y cambiar de plan usan el mismo formulario.
    const [eligiendo, setEligiendo] = useState(false);
    const [cambiandoPlan, setCambiandoPlan] = useState(false);
    // El odómetro de inicio, abierto desde el aviso antes de elegir destino.
    const [capturandoInicio, setCapturandoInicio] = useState(false);
    // La revisión de End Work con un viaje en ruta (D-07).
    const [revisandoCierre, setRevisandoCierre] = useState(false);
    const ultimaJornada = useRef<WorkSession | null>(null);

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

            if (!viaje) {
                setView({ phase: 'working', session: sesion });
                return;
            }
            if (viaje.status === 'planning') {
                setView({ phase: 'planning', session: sesion, trip: viaje });
                return;
            }
            if (viaje.status === 'in_transit') {
                setView({ phase: 'on-route', session: sesion, trip: viaje });
                return;
            }
            setView({ phase: 'arrived', session: sesion, trip: viaje });
        } catch {
            // Sin servidor se infiere de lo pendiente, sin inventar un viaje:
            // lo único que se puede afirmar sin red es que hay algo encolado.
            const pendientes = await listPendingActions().catch(() => []);
            if (pendientes.some((a) => a.kind === 'worksession.start')) {
                setView({ phase: 'start-queued' });
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

    const iniciarJornada = () => ejecutar(queueStartWork, 'Your workday could not be started.');

    const planificar = async (plan: TripPlanInput) => {
        const ok = await ejecutar(() => queuePlanTrip(plan), 'This trip could not be prepared.');
        if (ok) setEligiendo(false);
    };

    const arrancarViaje = (trip: Trip) => ejecutar(() => queueStartTrip(trip.id), 'This trip could not be started.');

    const llegar = (trip: Trip) => ejecutar(() => queueArrive(trip.id), 'Your arrival could not be recorded.');

    const cambiarPlan = async (trip: Trip, plan: TripPlanInput) => {
        const ok = await ejecutar(() => changeTripPlan(trip.id, plan), 'The plan could not be changed.');
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

    const inicio: OdometerEvidence | null = odometro?.start ?? null;
    const faltaInicio = inicio !== null && !isOdometerResolved(inicio.status);
    const capturandoOdometro = capturandoInicio && inicio !== null;
    const distancia = readingAsNumber(odometro?.odometer_distance);

    /** Vuelve al flujo que estaba en marcha, sin volver a elegir destino. */
    const odometroResuelto = async () => {
        setCapturandoInicio(false);
        await reconcile();
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
                        {faltaInicio && !capturandoInicio && !eligiendo && inicio && (
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
                                onCancel={() => setCapturandoInicio(false)}
                            />
                        )}

                        {!capturandoOdometro && eligiendo && (
                            <TripContextPicker
                                busy={busy}
                                confirmLabel="Prepare trip"
                                onCancel={() => setEligiendo(false)}
                                onConfirm={planificar}
                            />
                        )}

                        {!capturandoOdometro && !eligiendo && (
                            <>
                                <Button
                                    size="lg"
                                    className="h-16 w-full text-lg"
                                    disabled={busy}
                                    onClick={() => setEligiendo(true)}
                                >
                                    Where to next?
                                </Button>
                                <Button
                                    variant="outline"
                                    size="lg"
                                    className="h-14 w-full"
                                    disabled={busy}
                                    onClick={() => cerrarJornada(view.session)}
                                >
                                    End Work
                                </Button>
                            </>
                        )}
                    </div>
                )}

                {view.phase === 'planning' && (
                    <div className="flex flex-col gap-6">
                        <Cabecera session={view.session} />
                        {/* El plan se queda a la vista mientras se resuelve la
                            lectura, y al confirmarla se vuelve exactamente a
                            este mismo viaje: no se pierde lo ya elegido. */}
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

                        {/* Un viaje preparado no es un viaje empezado: desde
                            aquí también se puede terminar el día. Sin esto,
                            quien eligiera destino y no pudiera resolver el
                            odómetro se quedaba sin salida en la pantalla. */}
                        <Button
                            variant="ghost"
                            size="lg"
                            className="h-12 w-full"
                            disabled={busy}
                            onClick={() => cerrarJornada(view.session)}
                        >
                            End Work
                        </Button>
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

                {view.phase === 'arrived' && (
                    <div className="flex flex-col gap-6">
                        <Cabecera session={view.session} />
                        <Destino trip={view.trip} />
                        {/* Lo que se hace al llegar es RTE05. Un espacio
                            reservado explícito evita el callejón sin salida sin
                            fingir una función que no existe. */}
                        <NotBuiltYet feature="Activities" checkpoint="RTE05" />
                        <Button
                            variant="outline"
                            size="lg"
                            className="h-14 w-full"
                            disabled={busy}
                            onClick={() => cerrarJornada(view.session)}
                        >
                            End Work
                        </Button>
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
