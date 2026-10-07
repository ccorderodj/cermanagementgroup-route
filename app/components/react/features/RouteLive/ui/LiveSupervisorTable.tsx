import {
    LIVE_STATUS_LABEL, LIVE_STATUS_TONE, formatMiles, formatSince,
    type LiveSupervisor,
} from '@/entities/RouteLive';

/**
 * La lista de supervisores: la superficie operativa principal de V0.7.
 *
 * Es una tabla con las cinco columnas aprobadas —Supervisor, Miles today,
 * Status, Current / last activity, Since— y se escribe aquí en vez de pasar por
 * `DataTable` a propósito: aquélla aporta ordenación, filtros y paginación, y
 * ninguna de las tres está en la línea base. Traerla significaría añadir
 * controles que el mockup no tiene, que es justo lo que §14 prohíbe.
 */
interface LiveSupervisorTableProps {
    supervisors: LiveSupervisor[];
    selectedId: number | null;
    onSelect: (id: number) => void;
}

const COLUMNAS = [
    'Supervisor', 'Miles today', 'Status', 'Current / last activity', 'Since',
];

export function LiveSupervisorTable(props: LiveSupervisorTableProps) {
    const { supervisors, selectedId, onSelect } = props;

    return (
        <section
            className="rounded-lg border border-border bg-card"
        >
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
                <div>
                    <h3 className="text-base font-semibold text-foreground">
                        Supervisors
                    </h3>
                    <p className="text-xs text-muted-foreground">
                        Select a supervisor to inspect current activity
                    </p>
                </div>
            </div>

            <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                    <thead>
                        <tr>
                            {COLUMNAS.map((c) => (
                                <th
                                    key={c}
                                    className="whitespace-nowrap px-5 py-3 text-left text-[11px] font-medium uppercase tracking-wide text-muted-foreground"
                                >
                                    {c}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {supervisors.map((s) => (
                            <tr
                                key={s.user_id}
                                data-supervisor={s.user_id}
                                onClick={() => onSelect(s.user_id)}
                                className={`cursor-pointer border-t border-border transition-colors hover:bg-muted/50 ${
                                    selectedId === s.user_id ? 'bg-muted' : ''
                                }`}
                            >
                                <td className="px-5 py-3">
                                    <div className="flex items-center gap-3">
                                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                                            {s.initials}
                                        </span>
                                        <span className="flex flex-col">
                                            <b className="font-medium text-foreground">
                                                {s.name}
                                            </b>
                                            <small className="text-xs text-muted-foreground">
                                                {s.vehicle_label || '—'}
                                            </small>
                                        </span>
                                    </div>
                                </td>
                                <td className="whitespace-nowrap px-5 py-3 font-medium text-foreground">
                                    {formatMiles(s.official_miles)}
                                    {/*
                                      * Pendiente no es cero. Un total que
                                      * presenta un viaje sin calcular como cero
                                      * millas parece final y no lo es.
                                      */}
                                    {s.mileage_pending && (
                                        <span className="ml-1 text-xs font-normal text-muted-foreground">
                                            + pending
                                        </span>
                                    )}
                                    {/*
                                      * Y un cero sin explicacion tampoco es
                                      * cero. Un viaje que termino sin poder
                                      * medirse se dibujaba igual que no haber
                                      * conducido; esto los separa sin inventar
                                      * ninguna distancia.
                                      */}
                                    {s.mileage_unresolved > 0 && (
                                        <span className="ml-1 text-xs font-normal text-muted-foreground">
                                            {`· ${s.mileage_unresolved} unresolved`}
                                        </span>
                                    )}
                                </td>
                                <td className="whitespace-nowrap px-5 py-3">
                                    <span className="inline-flex items-center gap-2 text-foreground">
                                        <i
                                            className={`h-2 w-2 rounded-full ${LIVE_STATUS_TONE[s.status]}`}
                                        />
                                        {LIVE_STATUS_LABEL[s.status]}
                                    </span>
                                </td>
                                <td className="px-5 py-3">
                                    <b className="font-medium text-foreground">
                                        {s.activity_label || '—'}
                                    </b>
                                    {s.activity_reference && (
                                        <div className="text-xs text-muted-foreground">
                                            {s.activity_reference}
                                        </div>
                                    )}
                                </td>
                                <td className="whitespace-nowrap px-5 py-3 text-muted-foreground">
                                    {formatSince(s.since)}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>

                {supervisors.length === 0 && (
                    <p className="px-5 py-10 text-center text-sm text-muted-foreground">
                        No supervisors are set up for this company yet.
                    </p>
                )}
            </div>
        </section>
    );
}
