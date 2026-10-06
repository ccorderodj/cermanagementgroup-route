import { Card } from '@/shared/ui/shadcn/new-york';
import {
    formatDuration,
    formatGroupLabel,
    formatMiles,
    formatPeriod,
    type ExplorerGroup,
    type ExplorerGroupedBy,
    type ExplorerRange,
} from '@/entities/RouteActivityExplorer';

/**
 * Las filas de grupo del nivel actual, como `groupRows()` de la línea base.
 *
 * La estructura es la del mockup y no una tabla: una tarjeta con el título del
 * periodo, la pista `Grouped by <nivel>`, la insignia `N groups`, y una lista
 * de **botones** —cada fila baja un nivel— con el nombre a la izquierda y las
 * millas más `· View <nivel>` a la derecha.
 *
 * Que la fila sea un botón es parte del producto, no decoración: es el
 * mecanismo de desglose `Year → Month → Week → Day` que §2.4 manda tomar del
 * mockup en vez de inventar un acordeón o un árbol de migas.
 *
 * El combustible estimado
 * ------------------------
 * La línea base enseña aquí un coste (`$47.23 est. fuel`). CER decidió en D-01
 * —durante RTE07— que el hueco se conserva con el valor neutro mientras no
 * exista una fuente autorizada de precio por galón. Así que se mantiene el
 * hueco y se enseña `—`: un coste calculado con un precio inventado se lee
 * como un hecho y nadie sabría que no lo es.
 */
interface ExplorerGroupListProps {
    range: ExplorerRange;
    start: string;
    end: string;
    groupedBy: ExplorerGroupedBy;
    groups: ExplorerGroup[];
    onDrill: (group: ExplorerGroup) => void;
}

export function ExplorerGroupList({
    range,
    start,
    end,
    groupedBy,
    groups,
    onDrill,
}: ExplorerGroupListProps) {
    return (
        <Card className="p-5">
            <div className="flex items-start justify-between gap-4 pb-3.5">
                <div>
                    <h3 className="text-base font-semibold text-foreground">
                        {formatPeriod(range, start, end)}
                    </h3>
                    <div className="text-xs text-muted-foreground">
                        Grouped by {groupedBy}
                    </div>
                </div>
                <span className="inline-flex items-center rounded-full bg-muted px-2 py-1 text-[11px] font-extrabold text-muted-foreground">
                    {groups.length} groups
                </span>
            </div>

            {groups.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                    No recorded activity in this period.
                </p>
            ) : (
                <div className="grid gap-2.5">
                    {groups.map((g) => (
                        <button
                            key={g.start}
                            type="button"
                            onClick={() => onDrill(g)}
                            className="flex w-full items-center justify-between gap-3 rounded-xl border border-border bg-card p-3.5 text-left"
                        >
                            <div>
                                <b className="block text-sm font-semibold text-foreground">
                                    {formatGroupLabel(groupedBy, g)}
                                </b>
                                <small className="text-xs text-muted-foreground">
                                    {g.activities} activities ·{' '}
                                    {formatDuration(g.activity_seconds, g.has_open_activity)}
                                </small>
                            </div>
                            <div className="text-right">
                                <strong className="block text-sm font-semibold text-foreground">
                                    {formatMiles(g.official_miles)} mi
                                    {g.mileage_pending && (
                                        <span className="ml-1 text-xs font-normal text-muted-foreground">
                                            + pending
                                        </span>
                                    )}
                                </strong>
                                <span className="block max-w-[125px] text-xs text-muted-foreground md:max-w-none">
                                    — est. fuel · View {groupedBy}
                                </span>
                            </div>
                        </button>
                    ))}
                </div>
            )}
        </Card>
    );
}
