import { Card } from '@/shared/ui/shadcn/new-york';
import {
    formatDuration,
    formatGroupLabel,
    formatMiles,
} from '@/entities/RouteActivityExplorer';
import { formatMoney, type ReportGroup } from '@/entities/RouteReports';

/**
 * La tarjeta izquierda del V0.7: *By day / By week / By month* según el rango,
 * con *«Time grouping follows Activity exploration»*. Las etiquetas de cada fila
 * son las del explorador —`Mon Sep 14`, `Sep 1–6`, `January`— porque el
 * agrupamiento es el suyo.
 *
 * Desde RTE09 E01 cada fila **se puede elegir**: acota el *Activity breakdown*
 * de la derecha a ese día, semana o mes. Los KPIs no cambian. Volver a pulsar la
 * fila elegida, o *Whole …*, devuelve el desglose al periodo entero.
 *
 * Son botones (`aria-pressed`), operables con teclado, y la fila elegida no se
 * distingue sólo por el color: lleva la marca *Selected*.
 */
const TITULO: Record<string, string> = { day: 'By day', week: 'By week', month: 'By month' };

/** El nombre del periodo entero, para volver a él. */
const ENTERO: Record<string, string> = { day: 'week', week: 'month', month: 'year' };

/** El patrón de elemento elegido del producto (`IntegrationGuideSheet`). */
const ELEGIDA = 'border-primary bg-primary/5';

const FILA = [
    'flex w-full items-center justify-between gap-3 rounded-xl border p-3.5 text-left',
    'transition-colors hover:bg-accent/40',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
].join(' ');

interface ReportsTimelineProps {
    groupedBy: 'day' | 'week' | 'month';
    groups: ReportGroup[];
    /** Inicio del subgrupo elegido; `null`: el periodo entero. */
    selectedStart: string | null;
    onSelect: (start: string | null) => void;
}

export function ReportsTimeline({
    groupedBy,
    groups,
    selectedStart,
    onSelect,
}: ReportsTimelineProps) {
    return (
        <Card className="p-5">
            <div className="flex items-start justify-between gap-3 pb-3.5">
                <div>
                    <h3 className="text-base font-semibold text-foreground">{TITULO[groupedBy]}</h3>
                    <div className="text-xs text-muted-foreground">
                        Time grouping follows Activity exploration
                    </div>
                </div>
                {selectedStart && (
                    <button
                        type="button"
                        onClick={() => onSelect(null)}
                        className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-foreground hover:bg-accent"
                    >
                        Whole {ENTERO[groupedBy]}
                    </button>
                )}
            </div>
            {groups.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                    No recorded activity in this period.
                </p>
            ) : (
                <div className="grid gap-2.5">
                    {groups.map((g) => {
                        const elegida = g.start === selectedStart;
                        return (
                            <button
                                key={g.start}
                                type="button"
                                aria-pressed={elegida}
                                data-group-start={g.start}
                                onClick={() => onSelect(elegida ? null : g.start)}
                                className={`${FILA} ${elegida ? ELEGIDA : 'border-border bg-card'}`}
                            >
                                <div>
                                    <b className="block text-sm font-semibold text-foreground">
                                        {formatGroupLabel(groupedBy, { ...g, drill_date: g.start })}
                                        {elegida && (
                                            <span className="ml-2 rounded-full bg-primary px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary-foreground">
                                                Selected
                                            </span>
                                        )}
                                    </b>
                                    <small className="text-xs text-muted-foreground">
                                        {g.activities} {g.activities === 1 ? 'activity' : 'activities'} ·{' '}
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
                                    <span className="text-xs text-muted-foreground">
                                        {formatMoney(g.estimated_fuel_cost)} est. fuel
                                    </span>
                                </div>
                            </button>
                        );
                    })}
                </div>
            )}
        </Card>
    );
}
