import { formatDuration, formatMiles } from '@/entities/RouteActivityExplorer';
import { formatMoney, type ReportMetrics } from '@/entities/RouteReports';

/**
 * Las cuatro tarjetas del V0.7, en su orden: Total miles, Activity time,
 * Activities, Est. fuel cost. Cuatro columnas en escritorio y dos en pantallas
 * estrechas (`@media(max-width:1050px)` y móvil del V0.7).
 *
 * El coste se pinta tal como llega: `$0.00` mientras falta la referencia de
 * precio, que es la decisión de producto. No se sustituye por otra cosa aquí.
 */
export function ReportsKpis({ summary }: { summary: ReportMetrics }) {
    const casillas: { etiqueta: string; valor: string }[] = [
        {
            etiqueta: 'Total miles',
            valor: `${formatMiles(summary.official_miles)}${summary.mileage_pending ? ' +' : ''}`,
        },
        {
            etiqueta: 'Activity time',
            valor: formatDuration(summary.activity_seconds, summary.has_open_activity),
        },
        { etiqueta: 'Activities', valor: String(summary.activities) },
        { etiqueta: 'Est. fuel cost', valor: formatMoney(summary.estimated_fuel_cost) },
    ];

    return (
        <div className="mb-4 grid grid-cols-2 gap-2.5 xl:grid-cols-4 xl:gap-4">
            {casillas.map((c) => (
                <div
                    key={c.etiqueta}
                    className="rounded-xl border border-border bg-card p-4"
                    data-kpi={c.etiqueta}
                >
                    <div className="text-xs uppercase tracking-wide text-muted-foreground">
                        {c.etiqueta}
                    </div>
                    <div className="mt-1 text-2xl font-semibold text-foreground">{c.valor}</div>
                </div>
            ))}
        </div>
    );
}
