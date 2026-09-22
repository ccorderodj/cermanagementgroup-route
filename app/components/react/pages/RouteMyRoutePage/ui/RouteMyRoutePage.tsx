import { NotBuiltYet, RouteMobileShell } from '@/widgets/RouteShell';

/**
 * Pantalla principal del supervisor.
 *
 * En RTE02 es **sólo el shell**. La jornada —Start Work, el viaje, la
 * actividad— es de RTE03 a RTE05, y hasta entonces esta pantalla lo dice en vez
 * de enseñar un botón "Start Work" que no haría nada. Un control que no
 * responde es peor que su ausencia: el supervisor lo pulsa, no pasa nada, y
 * deja de confiar en el resto.
 */
const RouteMyRoutePage = () => (
    <RouteMobileShell title="My Route" active="my-route">
        <div data-testid="RouteMyRoutePage" className="flex flex-col gap-4">
            <NotBuiltYet
                feature="The workday (Start Work, Trips, Activities)"
                checkpoint="RTE03-RTE05"
            />
        </div>
    </RouteMobileShell>
);

export default RouteMyRoutePage;
