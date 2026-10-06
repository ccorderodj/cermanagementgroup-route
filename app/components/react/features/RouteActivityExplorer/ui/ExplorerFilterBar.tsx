import {
    EXPLORER_RANGES,
    type ExplorerRange,
    type ExplorerSupervisor,
} from '@/entities/RouteActivityExplorer';

/**
 * La barra de filtros de la línea base: supervisor, fecha y las pestañas.
 *
 * Son **exactamente** los tres controles del mockup y ninguno más. FR-07 lo
 * dice sin margen: no se inventan filtros en este checkpoint, y que Reports
 * vaya a filtrar por otras cosas más adelante no es permiso para adelantarlo
 * aquí.
 *
 * Por qué en móvil desaparecen dos
 * ---------------------------------
 * No es una simplificación mía. El mockup tiene un ámbito móvil explícito y
 * dice:
 *
 *     .app.device-mobile .filterbar     { display: block }
 *     .app.device-mobile .fields-inline { display: none }
 *
 * es decir, en móvil la barra se apila y el **selector de supervisor y la
 * fecha no se muestran**; sólo quedan las pestañas de rango. Y es específico de
 * esta pantalla: en Reports el mismo mockup los vuelve a mostrar
 * (`.report-toolbar .fields-inline { display: block }`). Reproducirlo es
 * fidelidad; añadirlos "porque son útiles" sería rediseñar.
 */
interface ExplorerFilterBarProps {
    supervisors: ExplorerSupervisor[];
    supervisorUserId: number | null;
    onSupervisorChange: (userId: number) => void;
    date: string;
    onDateChange: (date: string) => void;
    range: ExplorerRange;
    onRangeChange: (range: ExplorerRange) => void;
    /** En móvil los dos campos no se dibujan, como en la línea base. */
    showFields?: boolean;
}

export function ExplorerFilterBar({
    supervisors,
    supervisorUserId,
    onSupervisorChange,
    date,
    onDateChange,
    range,
    onRangeChange,
    showFields = true,
}: ExplorerFilterBarProps) {
    return (
        <div className="mb-4 flex flex-col items-stretch gap-3 md:flex-row md:items-end md:justify-between">
            {showFields && (
                <div className="flex gap-3">
                    <div className="flex flex-col gap-1">
                        <label
                            htmlFor="explorer-supervisor"
                            className="text-xs font-medium text-muted-foreground"
                        >
                            Supervisor
                        </label>
                        <select
                            id="explorer-supervisor"
                            className="h-9 rounded-md border border-border bg-card px-3 text-sm text-foreground"
                            value={supervisorUserId ?? ''}
                            onChange={(e) => onSupervisorChange(Number(e.target.value))}
                        >
                            {supervisors.map((s) => (
                                <option key={s.user_id} value={s.user_id}>
                                    {s.name}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div className="flex flex-col gap-1">
                        <label
                            htmlFor="explorer-date"
                            className="text-xs font-medium text-muted-foreground"
                        >
                            Date
                        </label>
                        <input
                            id="explorer-date"
                            type="date"
                            className="h-9 rounded-md border border-border bg-card px-3 text-sm text-foreground"
                            value={date}
                            onChange={(e) => onDateChange(e.target.value)}
                        />
                    </div>
                </div>
            )}

            <div className="flex gap-0.5 rounded-xl bg-muted p-1">
                {EXPLORER_RANGES.map((r) => (
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
        </div>
    );
}
