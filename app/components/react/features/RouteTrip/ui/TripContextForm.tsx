import { useEffect, useState } from 'react';
import {
    Button, Input, Label, Select, SelectContent, SelectItem,
    SelectTrigger, SelectValue,
} from '@/shared/ui/shadcn/new-york';
import { TRIP_CONTEXTS, type TripPlanInput, type TripPurpose } from '@/entities/RouteTrips';
import { fetchStandardValues, type StandardValue } from '@/entities/RouteStandardValues';

/**
 * Lo que ese contexto necesita antes de salir, y nada más.
 *
 * Una sola pantalla
 * -----------------
 * El contexto ya está elegido cuando se llega aquí, así que esto pide sus
 * campos y ofrece **Start Trip** como acción principal. No hay un paso
 * intermedio que repita el destino y vuelva a preguntar: preparar un viaje y
 * empezarlo son la misma decisión del supervisor, y partirla en dos pantallas
 * añadía una pulsación sin añadir información (PD-05).
 *
 * Qué pide cada contexto sale de `TRIP_CONTEXTS`, no de un `if` aquí: el texto
 * libre es texto libre por decisión de CER, y sólo tres contextos llevan valor
 * de lista, obligatorio antes de salir.
 *
 * Sin `End Work`
 * --------------
 * Salir del día no se ofrece desde aquí (FR-11). `Back` devuelve al workbench,
 * que es el único sitio canónico para terminar la jornada. Un atajo aquí sería
 * una salida ambigua a mitad de una decisión a medio tomar.
 */

interface TripContextFormProps {
    purpose: TripPurpose;
    busy?: boolean;
    /** Plan de partida, al cambiar de plan sobre un viaje en curso. */
    initial?: TripPlanInput | null;
    confirmLabel: string;
    backLabel?: string;
    onBack: () => void;
    onConfirm: (plan: TripPlanInput) => void;
}

export function TripContextForm(props: TripContextFormProps) {
    const {
        purpose, busy, initial, confirmLabel, backLabel = 'Back', onBack, onConfirm,
    } = props;

    const contexto = TRIP_CONTEXTS[purpose];

    const [reference, setReference] = useState(initial?.context_reference ?? '');
    const [valueId, setValueId] = useState<string>(
        initial?.standard_value_id ? String(initial.standard_value_id) : '',
    );
    const [opciones, setOpciones] = useState<StandardValue[]>([]);
    const [cargando, setCargando] = useState(false);

    useEffect(() => {
        if (!contexto.standardList) {
            setOpciones([]);
            return;
        }
        setCargando(true);
        fetchStandardValues(contexto.standardList)
            .then(setOpciones)
            .catch(() => setOpciones([]))
            .finally(() => setCargando(false));
    }, [contexto.standardList]);

    // El valor de lista es obligatorio donde aplica. El servidor lo exige
    // igualmente; deshabilitar el botón sólo evita ofrecer algo que va a fallar.
    const listo = !contexto.standardList || Boolean(valueId);

    return (
        <div className="flex flex-col gap-4" data-testid="TripContextForm">
            <p className="text-center text-base font-medium text-foreground">
                {contexto.label}
            </p>

            {contexto.standardList && (
                <div className="flex flex-col gap-1.5">
                    <Label htmlFor="trip-standard-value">
                        {contexto.standardLabel}
                    </Label>
                    <Select value={valueId} onValueChange={setValueId}>
                        <SelectTrigger id="trip-standard-value" className="h-12">
                            <SelectValue
                                placeholder={cargando ? 'Loading…' : 'Choose one'}
                            />
                        </SelectTrigger>
                        <SelectContent>
                            {opciones.map((opcion) => (
                                <SelectItem key={opcion.id} value={String(opcion.id)}>
                                    {opcion.label}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
            )}

            {contexto.freeTextLabel && (
                <div className="flex flex-col gap-1.5">
                    <Label htmlFor="trip-reference">
                        {contexto.freeTextLabel}
                        <span className="ml-1 text-muted-foreground">(optional)</span>
                    </Label>
                    <Input
                        id="trip-reference"
                        className="h-12"
                        value={reference}
                        onChange={(e) => setReference(e.target.value)}
                        placeholder={contexto.freeTextLabel}
                    />
                </div>
            )}

            <Button
                size="lg"
                className="h-16 w-full text-lg"
                disabled={busy || !listo}
                onClick={() => onConfirm({
                    purpose,
                    context_reference: reference.trim() || null,
                    standard_value_id: valueId ? Number(valueId) : null,
                })}
            >
                {confirmLabel}
            </Button>

            {/* `secondary` y no `ghost`: en texto plano no se leía como botón.
                Y no `outline` ni nada más fuerte, porque la acción principal de
                esta pantalla es salir de viaje — volver atrás tiene que verse,
                sin disputarle el sitio. */}
            <Button
                variant="secondary"
                className="h-12 w-full"
                disabled={busy}
                onClick={onBack}
            >
                {backLabel}
            </Button>
        </div>
    );
}
