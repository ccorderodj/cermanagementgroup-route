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
 * Qué se ve en móvil (H-1)
 * ------------------------
 * El mockup V0.7 ocultaba en móvil los dos campos:
 *
 *     .app.device-mobile .filterbar     { display: block }
 *     .app.device-mobile .fields-inline { display: none }
 *
 * y así se construyó. En campo eso dejaba a un administrador en el teléfono
 * mirando siempre al primer supervisor de la lista, sin forma de cambiarlo.
 * El PO autorizó en H-1 una excepción **acotada** a esa regla: el selector de
 * supervisor existente se muestra también en móvil. **Sólo él**: la fecha
 * sigue oculta, como en la línea base, porque la excepción no la incluye. Por
 * eso ya no hay un único interruptor para los dos campos.
 *
 * En escritorio nada cambia: los dos campos, en la misma fila y con el mismo
 * ancho. En móvil el selector ocupa el ancho de la barra, que es donde cabe sin
 * desbordar y donde se pulsa con el dedo.
 *
 * La actividad propia (`/route/activity`) no tiene selector de supervisor
 * (`showSupervisor={false}`): no hay a quién elegir.
 */
interface ExplorerFilterBarProps {
    supervisors: ExplorerSupervisor[];
    supervisorUserId: number | null;
    onSupervisorChange: (userId: number) => void;
    date: string;
    onDateChange: (date: string) => void;
    range: ExplorerRange;
    onRangeChange: (range: ExplorerRange) => void;
    /**
     * La fecha no se dibuja en móvil, como en la línea base. El selector de
     * supervisor se dibuja siempre (H-1).
     */
    showDate?: boolean;
    /** `false` en la actividad propia: sin selector ni directorio. */
    showSupervisor?: boolean;
}

export function ExplorerFilterBar({
    supervisors,
    supervisorUserId,
    onSupervisorChange,
    date,
    onDateChange,
    range,
    onRangeChange,
    showDate = true,
    showSupervisor = true,
}: ExplorerFilterBarProps) {
    return (
        <div className="mb-4 flex flex-col items-stretch gap-3 md:flex-row md:items-end md:justify-between">
            {(showSupervisor || showDate) && (
                <div className="flex gap-3">
                    {showSupervisor && (
                        <div className="flex min-w-0 flex-1 flex-col gap-1 md:flex-initial">
                            <label
                                htmlFor="explorer-supervisor"
                                className="text-xs font-medium text-muted-foreground"
                            >
                                Supervisor
                            </label>
                            <select
                                id="explorer-supervisor"
                                className="h-9 w-full rounded-md border border-border bg-card px-3 text-sm text-foreground md:w-auto"
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
                    )}
                    {showDate && (
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
                    )}
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
