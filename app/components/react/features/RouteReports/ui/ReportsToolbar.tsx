import {
    REPORT_RANGES,
    type ReportRange,
    type ReportSupervisor,
} from '@/entities/RouteReports';

/**
 * La barra de Reports del V0.7: supervisor, pestañas y la leyenda del periodo.
 *
 * A diferencia de Activity, **en Reports el V0.7 sí muestra el selector en
 * móvil** (`.app.device-mobile .report-toolbar .fields-inline{display:block}`):
 * la barra sólo se apila. Y no hay navegación entre periodos: se ve el en curso.
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
}

const TODOS = 'all';

export function ReportsToolbar({
    supervisors,
    supervisorUserId,
    onSupervisorChange,
    range,
    onRangeChange,
    legend,
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
        </div>
    );
}
