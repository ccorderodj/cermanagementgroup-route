import { Card } from '@/shared/ui/shadcn/new-york';
import {
    TRIP_PURPOSE_LABEL,
    formatDuration,
    formatMiles,
} from '@/entities/RouteActivityExplorer';
import { formatMoney, type ReportBreakdownRow } from '@/entities/RouteReports';

/**
 * La tarjeta derecha del V0.7: *Activity breakdown* por **propósito de viaje**
 * —Client Visit, Employee Visit, Recruiting, Check Delivery, Office, Other—
 * con Miles, Time, Events y Est. cost, y una barra proporcional a las millas.
 *
 * Es por propósito y no por actividad seleccionada (decisión D-4): un viaje
 * tiene un propósito, así que cada fila suma sus millas y su tiempo **una**
 * vez. Las actividades seleccionadas van al Excel.
 */
export function ReportsBreakdown({ rows }: { rows: ReportBreakdownRow[] }) {
    const millas = rows.map((r) => Number.parseFloat(String(r.official_miles)) || 0);
    const maximo = Math.max(1, ...millas);

    return (
        <Card className="p-5">
            <div className="pb-3.5">
                <h3 className="text-base font-semibold text-foreground">Activity breakdown</h3>
                <div className="text-xs text-muted-foreground">
                    Miles, time, events and estimated fuel by activity
                </div>
            </div>
            {rows.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                    No recorded activity in this period.
                </p>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-sm">
                        <thead>
                            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                                <th className="py-2 pr-3 font-medium">Activity</th>
                                <th className="py-2 pr-3 text-right font-medium">Miles</th>
                                <th className="py-2 pr-3 text-right font-medium">Time</th>
                                <th className="py-2 pr-3 text-right font-medium">Events</th>
                                <th className="py-2 text-right font-medium">Est. cost</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((r, i) => (
                                <tr key={r.purpose} className="border-b border-border last:border-0">
                                    <td className="py-2.5 pr-3">
                                        <b className="font-semibold text-foreground">
                                            {TRIP_PURPOSE_LABEL[r.purpose] ?? r.purpose}
                                        </b>
                                        <div className="mt-1 h-1.5 w-full rounded-full bg-muted">
                                            <i
                                                className="block h-1.5 rounded-full bg-primary"
                                                style={{ width: `${Math.max(8, (millas[i] / maximo) * 100)}%` }}
                                            />
                                        </div>
                                    </td>
                                    <td className="py-2.5 pr-3 text-right tabular-nums">
                                        {formatMiles(r.official_miles)}
                                    </td>
                                    <td className="py-2.5 pr-3 text-right tabular-nums">
                                        {formatDuration(r.activity_seconds, r.has_open_activity)}
                                    </td>
                                    <td className="py-2.5 pr-3 text-right tabular-nums">{r.activities}</td>
                                    <td className="py-2.5 text-right tabular-nums">
                                        {formatMoney(r.estimated_fuel_cost)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </Card>
    );
}
