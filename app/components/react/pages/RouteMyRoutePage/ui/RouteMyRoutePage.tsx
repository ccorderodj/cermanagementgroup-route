import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/shared/ui/shadcn/new-york';
import { NotBuiltYet, RouteMobileShell } from '@/widgets/RouteShell';
import {
    fetchCurrentWorkSession,
    queueEndWork,
    queueStartWork,
    syncPendingWorkSessionActions,
    type WorkSession,
} from '@/entities/RouteWorkSessions';
import { listPendingActions } from '@/shared/lib/offlineQueue';

/**
 * My Route: el espacio de trabajo del supervisor.
 *
 * RTE03 solo construye la Jornada. El viaje —Start Trip, On Route, Arrived—
 * es de RTE04, y hasta entonces esta pantalla lo dice con `NotBuiltYet` en
 * vez de simular un flujo que no existe.
 *
 * El estado nunca lo posee el cliente: cada apertura, reanudación o
 * reconexión llama a `GET /worksessions/current` y pinta lo que el servidor
 * responde (§12 de las instrucciones). Las únicas excepciones son las dos
 * fases "…-queued", que existen exclusivamente para cuando de verdad no hay
 * red — y en cuanto la hay, `reconcile()` las reemplaza por la verdad del
 * servidor.
 */

type ViewState =
    | { phase: 'loading' }
    | { phase: 'no-session' }
    | { phase: 'active'; session: WorkSession }
    | { phase: 'start-queued' }
    | { phase: 'end-queued'; session: WorkSession }
    | { phase: 'error' };

function formatearHora(iso: string): string {
    return new Date(iso).toLocaleTimeString(undefined, {
        hour: 'numeric',
        minute: '2-digit',
    });
}

const RouteMyRoutePage = () => {
    const [view, setView] = useState<ViewState>({ phase: 'loading' });
    const [busy, setBusy] = useState(false);
    // Última jornada real conocida, para poder seguir mostrando "desde qué
    // hora" mientras se está sin red esperando a terminar de sincronizar.
    const lastKnownSession = useRef<WorkSession | null>(null);

    const reconcile = useCallback(async () => {
        // Best-effort: si hay algo pendiente de una sesión anterior —la
        // aplicación se cerró antes de poder enviarlo—, se intenta primero.
        try {
            await syncPendingWorkSessionActions();
        } catch {
            // Sin red. Se sigue con lo que haya en el servidor o, si eso
            // también falla, con lo que diga la cola local más abajo.
        }

        try {
            const { work_session: sesion } = await fetchCurrentWorkSession();
            if (sesion) {
                lastKnownSession.current = sesion;
                setView({ phase: 'active', session: sesion });
                return;
            }

            const pendientes = await listPendingActions();
            const inicioEncolado = pendientes.some((a) => a.kind === 'worksession.start');
            setView(inicioEncolado ? { phase: 'start-queued' } : { phase: 'no-session' });
        } catch {
            // El servidor no respondió: se infiere el estado de la cola local
            // en vez de dejar la pantalla en blanco.
            const pendientes = await listPendingActions();
            const finEncolado = pendientes.some((a) => a.kind === 'worksession.end');
            const inicioEncolado = pendientes.some((a) => a.kind === 'worksession.start');

            if (finEncolado && lastKnownSession.current) {
                setView({ phase: 'end-queued', session: lastKnownSession.current });
            } else if (inicioEncolado) {
                setView({ phase: 'start-queued' });
            } else if (lastKnownSession.current) {
                setView({ phase: 'active', session: lastKnownSession.current });
            } else {
                setView({ phase: 'error' });
            }
        }
    }, []);

    useEffect(() => {
        reconcile();

        // Reabrir, reanudar o recuperar la conexión son los momentos en los
        // que el estado local puede haberse quedado atrás del servidor (§12):
        // cada uno vuelve a preguntar en vez de confiar en lo que ya se pintó.
        const alVolverVisible = () => {
            if (document.visibilityState === 'visible') reconcile();
        };
        document.addEventListener('visibilitychange', alVolverVisible);
        window.addEventListener('online', reconcile);

        return () => {
            document.removeEventListener('visibilitychange', alVolverVisible);
            window.removeEventListener('online', reconcile);
        };
    }, [reconcile]);

    const handleStartWork = async () => {
        setBusy(true);
        try {
            // Se confirma en IndexedDB antes de devolver el control: la
            // interfaz nunca enseña "aceptado" antes de que de verdad lo esté.
            await queueStartWork();
            setView({ phase: 'start-queued' });
            await reconcile();
        } finally {
            setBusy(false);
        }
    };

    const handleEndWork = async (session: WorkSession) => {
        setBusy(true);
        try {
            await queueEndWork(session.id);
            setView({ phase: 'end-queued', session });
            await reconcile();
        } finally {
            setBusy(false);
        }
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

                {view.phase === 'no-session' && (
                    <div className="flex flex-col items-center gap-6 py-16">
                        <p className="text-center text-sm text-muted-foreground">
                            Ready to start your day?
                        </p>
                        <Button
                            size="lg"
                            className="h-16 w-full max-w-xs text-lg"
                            disabled={busy}
                            onClick={handleStartWork}
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
                            This will sync as soon as you have a connection. You can
                            keep using the app.
                        </p>
                    </div>
                )}

                {(view.phase === 'active' || view.phase === 'end-queued') && (
                    <div className="flex flex-col gap-6">
                        <section className="rounded-lg border border-border bg-card p-5 text-center">
                            <p className="text-xs uppercase tracking-wide text-muted-foreground">
                                Working since
                            </p>
                            <p className="mt-1 text-2xl font-semibold text-foreground">
                                {formatearHora(view.session.started_at)}
                            </p>
                            {view.session.vehicle_id && (
                                <p className="mt-2 text-sm text-muted-foreground">
                                    Vehicle assigned for today
                                </p>
                            )}
                        </section>

                        {/* El viaje llega en RTE04. Hasta entonces, un espacio
                            reservado explícito evita un callejón sin salida en
                            la interfaz sin fingir una función que no existe. */}
                        <NotBuiltYet feature="Trips" checkpoint="RTE04" />

                        {view.phase === 'active' && (
                            <Button
                                variant="outline"
                                size="lg"
                                className="h-14 w-full"
                                disabled={busy}
                                onClick={() => handleEndWork(view.session)}
                            >
                                End Work
                            </Button>
                        )}

                        {view.phase === 'end-queued' && (
                            <p className="text-center text-sm text-muted-foreground">
                                Ending your day… this will sync as soon as you have a
                                connection.
                            </p>
                        )}
                    </div>
                )}
            </div>
        </RouteMobileShell>
    );
};

export default RouteMyRoutePage;
