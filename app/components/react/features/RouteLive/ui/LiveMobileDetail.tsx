import { Button } from '@/shared/ui/shadcn/new-york';
import {
    LIVE_STATUS_LABEL, LIVE_STATUS_TONE, formatSince, sufijoDeMillas,
    type LiveSupervisor,
} from '@/entities/RouteLive';

/**
 * El detalle móvil de `mobileSupervisorSummary()`: pantalla completa y vuelta.
 *
 * **No es el panel de escritorio encogido.** §2.3 y §14 lo prohíben de forma
 * explícita, y por eso la página elige entre las dos experiencias en vez de
 * renderizar la misma y dejar que el CSS la estruje: son dos presentaciones
 * aprobadas distintas, no una con dos anchos.
 *
 * La flecha de volver es un control real y devuelve a la lista con su contexto,
 * que es lo que la línea base llama `adminMobileDetail`.
 */
interface LiveMobileDetailProps {
    supervisor: LiveSupervisor;
    onBack: () => void;
}

export function LiveMobileDetail({ supervisor: s, onBack }: LiveMobileDetailProps) {
    return (
        <div className="flex flex-col gap-4">
            <div className="flex items-center gap-3">
                <Button
                    variant="ghost"
                    size="icon"
                    className="h-11 w-11 shrink-0 text-lg"
                    aria-label="Back to supervisors"
                    onClick={onBack}
                >
                    ←
                </Button>
                <div className="min-w-0">
                    <b className="block truncate font-medium text-foreground">
                        {s.name}
                    </b>
                    <div className="text-xs text-muted-foreground">
                        {`Today · ${Number(s.official_miles).toFixed(1)} mi`}
                        {sufijoDeMillas(s)}
                    </div>
                </div>
            </div>

            <div className="rounded-lg border border-border bg-card p-4">
                <span className="inline-flex items-center gap-2 text-sm text-foreground">
                    <i className={`h-2 w-2 rounded-full ${LIVE_STATUS_TONE[s.status]}`} />
                    {LIVE_STATUS_LABEL[s.status]}
                </span>
                <div className="mt-3 text-[11px] uppercase tracking-wide text-muted-foreground">
                    Current / last activity
                </div>
                <div className="mt-1 text-base font-medium text-foreground">
                    {s.activity_label || '—'}
                </div>
                <div className="text-sm text-muted-foreground">
                    {s.activity_reference || '—'}
                </div>
                <div className="mt-2 text-[11px] text-muted-foreground">
                    Since {formatSince(s)}
                </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-border bg-card p-3">
                    <b className="block text-lg font-semibold text-foreground">
                        {s.activities_today}
                    </b>
                    <span className="text-xs text-muted-foreground">
                        activities today
                    </span>
                </div>
                <div className="rounded-lg border border-border bg-card p-3">
                    <b className="block text-lg font-semibold text-muted-foreground">
                        —
                    </b>
                    <span className="text-xs text-muted-foreground">
                        estimated fuel
                    </span>
                </div>
            </div>

            <div className="rounded-lg border border-border bg-card p-4">
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    Vehicle
                </div>
                <div className="mt-1 text-sm text-foreground">
                    {s.vehicle_label || '—'}
                </div>
            </div>
        </div>
    );
}
