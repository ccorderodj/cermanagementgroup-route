import { useEffect, useState } from 'react';
import { RouteMobileShell } from '@/widgets/RouteShell';
import { fetchMySupervisorProfile } from '@/entities/RouteSupervisors';
import type { SupervisorProfile } from '@/entities/RouteSupervisors';

/**
 * Ficha del supervisor: quién es y qué vehículo conduce.
 *
 * El vehículo que se enseña aquí sale de la asignación vigente, resuelta en el
 * servidor. No hay copia en el perfil, así que lo que lee el supervisor es lo
 * mismo que ve el administrador: no pueden discrepar.
 *
 * Esta pantalla sí tiene datos reales en RTE02 —la asignación de vehículo es
 * parte de este checkpoint—, a diferencia de My Route y Activity.
 */
const RouteMePage = () => {
    const [profile, setProfile] = useState<SupervisorProfile | null>(null);
    const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');

    useEffect(() => {
        let cancelled = false;

        fetchMySupervisorProfile()
            .then((data) => {
                if (cancelled) return;
                setProfile(data);
                setState('ready');
            })
            .catch(() => {
                if (!cancelled) setState('error');
            });

        return () => { cancelled = true; };
    }, []);

    return (
        <RouteMobileShell title="Me" active="me">
            <div data-testid="RouteMePage" className="flex flex-col gap-4">
                {state === 'loading' && (
                    <p className="text-sm text-muted-foreground">Loading…</p>
                )}

                {state === 'error' && (
                    <p className="text-sm text-destructive">
                        Your profile could not be loaded. Try again later.
                    </p>
                )}

                {state === 'ready' && !profile && (
                    <div className="rounded-lg border border-border bg-card p-4">
                        <p className="font-medium text-foreground">
                            You are not registered as a Route supervisor
                        </p>
                        <p className="mt-1 text-sm text-muted-foreground">
                            An administrator has to add you before you can be
                            assigned a vehicle.
                        </p>
                    </div>
                )}

                {state === 'ready' && profile && (
                    <>
                        <section className="rounded-lg border border-border bg-card p-4">
                            <p className="text-xs uppercase tracking-wide text-muted-foreground">
                                Supervisor
                            </p>
                            <p className="mt-1 text-base font-semibold text-foreground">
                                {profile.first_name}
                                {' '}
                                {profile.last_name}
                            </p>
                            <p className="text-sm text-muted-foreground">{profile.email}</p>
                        </section>

                        <section className="rounded-lg border border-border bg-card p-4">
                            <p className="text-xs uppercase tracking-wide text-muted-foreground">
                                Assigned vehicle
                            </p>
                            {profile.current_vehicle ? (
                                <>
                                    <p className="mt-1 text-base font-semibold text-foreground">
                                        {profile.current_vehicle.year}
                                        {' '}
                                        {profile.current_vehicle.make}
                                        {' '}
                                        {profile.current_vehicle.model}
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                        Unit
                                        {' '}
                                        {profile.current_vehicle.unit}
                                        {' · '}
                                        {profile.current_vehicle.operational_mpg}
                                        {' MPG · '}
                                        {profile.current_vehicle.fuel_grade}
                                    </p>
                                </>
                            ) : (
                                /* Sin vehículo es un estado normal, no un error:
                                   un supervisor recién dado de alta todavía no
                                   conduce nada. */
                                <p className="mt-1 text-sm text-muted-foreground">
                                    No vehicle is assigned to you right now.
                                </p>
                            )}
                        </section>
                    </>
                )}
            </div>
        </RouteMobileShell>
    );
};

export default RouteMePage;
