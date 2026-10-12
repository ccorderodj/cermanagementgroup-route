import {
    REPORT_RANGES,
    formatReportPeriod,
    type ReportPeriod,
    type ReportRange,
    type ReportSupervisor,
} from '@/entities/RouteReports';

/**
 * La barra de Reports del V0.7: supervisor, pestañas y la leyenda del periodo.
 *
 * A diferencia de Activity, **en Reports el V0.7 sí muestra el selector en
 * móvil** (`.app.device-mobile .report-toolbar .fields-inline{display:block}`):
 * la barra sólo se apila.
 *
 * RTE09 E01 añade, junto a las pestañas, el **periodo concreto**: una semana
 * (`Oct 12–18, 2026`), un mes (`October 2026`) o un año (`2026`), según la
 * pestaña. Las opciones las da el servidor; no hay flechas anterior/siguiente.
 */
interface ReportsToolbarProps {
    supervisors: ReportSupervisor[];
    /** `null`: *All Supervisors*, el valor por defecto del V0.7. */
    supervisorUserId: number | null;
    onSupervisorChange: (userId: number | null) => void;
    range: ReportRange;
    onRangeChange: (range: ReportRange) => void;
    /** `All Supervisors · Sep 14–20, 2026`. */
    legend: string;
    /** Opciones del periodo concreto, de la más reciente a la más antigua. */
    periods: ReportPeriod[];
    /** Inicio del periodo mostrado; `null` mientras no hay datos. */
    periodStart: string | null;
    onPeriodChange: (start: string) => void;
}

/** La etiqueta del selector dice qué se elige: nunca un genérico «Period». */
const ETIQUETA: Record<ReportRange, string> = { week: 'Week', month: 'Month', year: 'Year' };

const TODOS = 'all';

export function ReportsToolbar({
    supervisors,
    supervisorUserId,
    onSupervisorChange,
    range,
    onRangeChange,
    legend,
    periods,
    periodStart,
    onPeriodChange,
}: ReportsToolbarProps) {
    return (
        <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-end">
            <div className="flex flex-col gap-1">
                <label
                    htmlFor="report-supervisor"
                    className="text-xs font-medium text-muted-foreground"
                >
                    Supervisor
                </label>
                <select
                    id="report-supervisor"
                    className="h-9 w-full rounded-md border border-border bg-card px-3 text-sm text-foreground md:w-auto"
                    value={supervisorUserId ?? TODOS}
                    onChange={(e) => onSupervisorChange(
                        e.target.value === TODOS ? null : Number(e.target.value),
                    )}
                >
                    <option value={TODOS}>All Supervisors</option>
                    {supervisors.map((s) => (
                        <option key={s.user_id} value={s.user_id}>
                            {s.name}
                        </option>
                    ))}
                </select>
            </div>
            <div>
                <div className="flex w-fit gap-0.5 rounded-xl bg-muted p-1">
                    {REPORT_RANGES.map((r) => (
                        <button
                            key={r}
                            type="button"
                            onClick={() => onRangeChange(r)}
                            className={
                                r === range
                                    ? 'rounded-lg bg-card px-3 py-1.5 text-sm font-semibold text-foreground shadow-sm'
                                    : 'rounded-lg px-3 py-1.5 text-sm text-muted-foreground'
                            }
                            aria-pressed={r === range}
                        >
                            {r.charAt(0).toUpperCase() + r.slice(1)}
                        </button>
                    ))}
                </div>
                <div className="mt-1.5 text-xs text-muted-foreground">{legend}</div>
            </div>
            <div className="flex flex-col gap-1">
                <label
                    htmlFor="report-period"
                    className="text-xs font-medium text-muted-foreground"
                >
                    {ETIQUETA[range]}
                </label>
                <select
                    id="report-period"
                    className="h-9 w-full rounded-md border border-border bg-card px-3 text-sm text-foreground md:w-auto"
                    value={periodStart ?? ''}
                    disabled={!periodStart}
                    onChange={(e) => onPeriodChange(e.target.value)}
                >
                    {!periodStart && <option value="">Loading…</option>}
                    {periods.map((p) => (
                        <option key={p.start} value={p.start}>
                            {formatReportPeriod(range, p.start, p.end)}
                        </option>
                    ))}
                </select>
            </div>
        </div>
    );
}
