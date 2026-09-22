import { NotBuiltYet, RouteMobileShell } from '@/widgets/RouteShell';

/**
 * Historial del supervisor.
 *
 * El Activity Explorer (Year -> Month -> Week -> Day -> Activity) llega en
 * RTE08, y depende de que antes exista la jornada que lo alimenta. Enseñar aquí
 * una jerarquía vacía daría la impresión de un módulo terminado sin datos, que
 * es distinto de un módulo que todavía no existe.
 */
const RouteActivityPage = () => (
    <RouteMobileShell title="Activity" active="activity">
        <div data-testid="RouteActivityPage" className="flex flex-col gap-4">
            <NotBuiltYet
                feature="The Activity Explorer"
                checkpoint="RTE08"
            />
        </div>
    </RouteMobileShell>
);

export default RouteActivityPage;
