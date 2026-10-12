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
 */
const TITULO: Record<string, string> = { day: 'By day', week: 'By week', month: 'By month' };

interface ReportsTimelineProps {
    groupedBy: 'day' | 'week' | 'month';
    groups: ReportGroup[];
}

export function ReportsTimeline({ groupedBy, groups }: ReportsTimelineProps) {
    return (
        <Card className="p-5">
            <div className="pb-3.5">
                <h3 className="text-base font-semibold text-foreground">{TITULO[groupedBy]}</h3>
                <div className="text-xs text-muted-foreground">
                    Time grouping follows Activity exploration
                </div>
            </div>
            {groups.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                    No recorded activity in this period.
                </p>
            ) : (
                <div className="grid gap-2.5">
                    {groups.map((g) => (
                        <div
                            key={g.start}
                            className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-3.5"
                        >
                            <div>
                                <b className="block text-sm font-semibold text-foreground">
                                    {formatGroupLabel(groupedBy, { ...g, drill_date: g.start })}
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
                        </div>
                    ))}
                </div>
            )}
        </Card>
    );
}
