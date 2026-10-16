import {
    LIVE_STATUS_LABEL, formatMiles, formatSince, motivoDeMillas,
    type LiveSupervisor,
} from '@/entities/RouteLive';

/**
 * La lista móvil de `mobileTodayList()`: una tarjeta por supervisor.
 *
 * Izquierda el nombre y el contexto —estado · actividad · referencia—, derecha
 * las millas y desde cuándo. Es la **misma información** que la tabla de
 * escritorio en la presentación compacta que la línea base aprobó, no un
 * recorte: §2.3 prohíbe simplificar la experiencia móvil por el hecho de que la
 * pantalla sea más pequeña.
 */
interface LiveMobileListProps {
    supervisors: LiveSupervisor[];
    onSelect: (id: number) => void;
}

export function LiveMobileList({ supervisors, onSelect }: LiveMobileListProps) {
    if (supervisors.length === 0) {
        return (
            <p className="py-10 text-center text-sm text-muted-foreground">
                No supervisors are set up for this company yet.
            </p>
        );
    }

    return (
        <div className="flex flex-col gap-2">
            {supervisors.map((s) => (
                <button
                    key={s.user_id}
                    type="button"
                    data-supervisor={s.user_id}
                    onClick={() => onSelect(s.user_id)}
                    className="flex min-h-14 w-full items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3 text-left"
                >
                    <span className="flex min-w-0 flex-col">
                        <b className="truncate font-medium text-foreground">
                            {s.name}
                        </b>
                        <span className="truncate text-xs text-muted-foreground">
                            {LIVE_STATUS_LABEL[s.status]}
                            {s.activity_label ? ` · ${s.activity_label}` : ''}
                            {s.activity_reference ? ` · ${s.activity_reference}` : ''}
                        </span>
                    </span>
                    <span className="flex shrink-0 flex-col items-end">
                        <b className="whitespace-nowrap font-medium text-foreground">
                            {formatMiles(s.official_miles)}
                        </b>
                        {/*
                          * El listado movil es la primera pantalla en telefono y
                          * no llevaba ningun motivo: ni `pending` ni `unresolved`.
                          * Un cero mudo aqui obliga a entrar supervisor por
                          * supervisor para averiguar si alguien condujo sin que
                          * se pudiera medir.
                          */}
                        {motivoDeMillas(s) && (
                            <span className="whitespace-nowrap text-xs text-muted-foreground">
                                {motivoDeMillas(s)}
                            </span>
                        )}
                        <span className="whitespace-nowrap text-xs text-muted-foreground">
                            Since {formatSince(s)}
                        </span>
                    </span>
                </button>
            ))}
        </div>
    );
}
