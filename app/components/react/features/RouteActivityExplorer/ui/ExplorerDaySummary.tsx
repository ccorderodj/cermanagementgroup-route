import {
    formatDuration,
    formatMiles,
    type ExplorerSummary,
} from '@/entities/RouteActivityExplorer';

/**
 * Las cuatro mini-estadísticas del día, en el orden de la línea base:
 * millas, tiempo de actividad, actividades y combustible estimado.
 *
 * El orden **es** parte de lo aprobado y no se reordena por estética. En móvil
 * el mockup las pone en dos columnas (`.app.device-mobile .summary-strip`), no
 * las elimina.
 *
 * El cuarto hueco enseña `—` por la decisión D-01 de CER: se conserva el slot
 * y no se inventa un precio por galón. Ver `ExplorerGroupList` para el porqué.
 */
interface ExplorerDaySummaryProps {
    summary: ExplorerSummary;
}

export function ExplorerDaySummary({ summary }: ExplorerDaySummaryProps) {
    const casillas: { valor: string; etiqueta: string }[] = [
        {
            valor: `${formatMiles(summary.official_miles)} mi${
                summary.mileage_pending ? ' +' : ''
            }`,
            etiqueta: 'miles',
        },
        {
            valor: formatDuration(summary.activity_seconds, summary.has_open_activity),
            etiqueta: 'activity time',
        },
        { valor: String(summary.activities), etiqueta: 'activities' },
        { valor: '—', etiqueta: 'estimated fuel' },
    ];

    return (
        <div className="mb-4 grid grid-cols-2 gap-2.5 xl:grid-cols-4">
            {casillas.map((c) => (
                <div
                    key={c.etiqueta}
                    className="rounded-xl border border-border bg-card p-3"
                >
                    <b className="block text-lg font-semibold text-foreground">
                        {c.valor}
                    </b>
                    <span className="text-xs text-muted-foreground">{c.etiqueta}</span>
                </div>
            ))}
        </div>
    );
}
