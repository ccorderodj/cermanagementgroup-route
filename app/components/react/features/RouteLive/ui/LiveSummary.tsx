import { Card } from '@/shared/ui/shadcn/new-york';
import { formatMiles, type LiveSummary as Resumen } from '@/entities/RouteLive';

/**
 * Las cuatro tarjetas del encabezado, en el orden y con las etiquetas de V0.7.
 *
 * El orden **es** parte de la línea base aprobada y no se reordena por estética:
 * primero cuánta gente está trabajando, luego las millas del día, y después el
 * desglose de en qué están. §14 lo prohíbe de forma explícita.
 *
 * En móvil las mismas cifras se presentan compactas, no se eliminan: la
 * información se condensa para que la lista de supervisores no caiga por debajo
 * del pliegue, que es la filosofía *list-first* de la línea base.
 */
interface LiveSummaryProps {
    summary: Resumen;
    compact?: boolean;
}

const TARJETAS = [
    {
        label: 'Supervisors working',
        valor: (s: Resumen) => String(s.supervisors_working),
        pista: (s: Resumen) => `of ${s.supervisors_total} active today`,
    },
    {
        label: 'Total miles today',
        valor: (s: Resumen) => Number(s.total_miles).toFixed(1),
        pista: () => 'across active routes',
    },
    {
        label: 'On route',
        valor: (s: Resumen) => String(s.on_route),
        pista: () => 'moving now',
    },
    {
        label: 'In activity',
        valor: (s: Resumen) => String(s.in_activity),
        pista: () => 'at destination',
    },
] as const;

export function LiveSummary({ summary, compact = false }: LiveSummaryProps) {
    if (compact) {
        return (
            <div
                className="grid grid-cols-2 gap-2"
            >
                {TARJETAS.map((t) => (
                    <div
                        key={t.label}
                        className="rounded-lg border border-border bg-card px-3 py-2"
                    >
                        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                            {t.label}
                        </div>
                        <div className="text-lg font-semibold text-foreground">
                            {t.valor(summary)}
                        </div>
                    </div>
                ))}
            </div>
        );
    }

    return (
        <div
            className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
        >
            {TARJETAS.map((t) => (
                <Card key={t.label} className="p-5">
                    <div className="text-xs uppercase tracking-wide text-muted-foreground">
                        {t.label}
                    </div>
                    <div className="mt-1 text-3xl font-semibold text-foreground">
                        {t.valor(summary)}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                        {t.pista(summary)}
                    </div>
                </Card>
            ))}
        </div>
    );
}

export { formatMiles };
