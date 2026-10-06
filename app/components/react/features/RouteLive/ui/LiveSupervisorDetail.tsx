import {
    LIVE_STATUS_LABEL, LIVE_STATUS_TONE, formatSince,
    type LiveSupervisor,
} from '@/entities/RouteLive';

/**
 * El panel lateral de escritorio, con la estructura de `supervisorDetail()`.
 *
 * Tres bloques, en el orden de la línea base: la cabecera con la persona y sus
 * millas, el contexto actual, y las dos mini-estadísticas.
 *
 * Sobre el combustible estimado
 * ------------------------------
 * V0.7 lo enseña como `millas / mpg × precio`. El **precio por galón no existe
 * en el dominio** —el catálogo lo reserva como `route.fuelreference.manage`,
 * una capacidad futura— así que aquí se presenta el estado neutro en vez de un
 * número inventado. El hueco se conserva para que el día que exista la
 * referencia se rellene sin tocar la maquetación aprobada. Está listado como
 * desviación en el reporte de entrega.
 */
interface LiveSupervisorDetailProps {
    supervisor: LiveSupervisor | null;
}

export function LiveSupervisorDetail({ supervisor }: LiveSupervisorDetailProps) {
    if (!supervisor) {
        return (
            <aside
                className="flex items-center justify-center rounded-lg border border-border bg-card p-6"
            >
                <p className="text-center text-sm text-muted-foreground">
                    Select a supervisor to inspect current activity.
                </p>
            </aside>
        );
    }

    const s = supervisor;

    return (
        <aside
            className="flex flex-col gap-4 rounded-lg border border-border bg-card p-5"
        >
            <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-3">
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">
                        {s.initials}
                    </span>
                    <div>
                        <b className="block font-medium text-foreground">{s.name}</b>
                        <span className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                            <i className={`h-2 w-2 rounded-full ${LIVE_STATUS_TONE[s.status]}`} />
                            {LIVE_STATUS_LABEL[s.status]}
                        </span>
                    </div>
                </div>
                <div className="text-right">
                    <div className="text-3xl font-semibold text-foreground">
                        {Number(s.official_miles).toFixed(1)}
                    </div>
                    <div className="text-xs text-muted-foreground">
                        {s.mileage_pending ? 'miles today · pending' : 'miles today'}
                    </div>
                </div>
            </div>

            <div className="rounded-md bg-muted/40 p-4">
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                    Current / last activity
                </div>
                <div className="mt-1 text-base font-medium text-foreground">
                    {s.activity_label || '—'}
                </div>
                <div className="text-sm text-muted-foreground">
                    {s.activity_reference || '—'}
                </div>
                <div className="mt-2 text-[11px] text-muted-foreground">
                    Since {formatSince(s.since)}
                </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
                <div className="rounded-md border border-border p-3">
                    <b className="block text-lg font-semibold text-foreground">
                        {s.activities_today}
                    </b>
                    <span className="text-xs text-muted-foreground">
                        activities today
                    </span>
                </div>
                <div className="rounded-md border border-border p-3">
                    <b className="block text-lg font-semibold text-muted-foreground">
                        —
                    </b>
                    <span className="text-xs text-muted-foreground">
                        estimated fuel
                    </span>
                </div>
            </div>
        </aside>
    );
}
