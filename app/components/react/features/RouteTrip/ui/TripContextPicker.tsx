import { useEffect, useState } from 'react';
import {
    Button, Input, Label, Select, SelectContent, SelectItem,
    SelectTrigger, SelectValue,
} from '@/shared/ui/shadcn/new-york';
import {
    TRIP_CONTEXTS, TRIP_PURPOSES,
    type TripPlanInput, type TripPurpose,
} from '@/entities/RouteTrips';
import { fetchStandardValues, type StandardValue } from '@/entities/RouteStandardValues';

/**
 * Elegir a qué se sale, y completar lo que ese contexto necesita.
 *
 * Dos pasos, uno por pantalla: primero el contexto, después sus datos. Es la
 * regla móvil de una sola acción principal a la vez — meter siete botones y un
 * formulario en la misma vista es exactamente lo que no se puede hacer con el
 * teléfono en la mano.
 *
 * Qué pide cada contexto sale de `TRIP_CONTEXTS`, no de un `if` aquí: el texto
 * libre es texto libre por decisión de CER, y sólo tres contextos llevan valor
 * de lista, obligatorio antes de salir. Los demás eligen lo suyo al llegar, y
 * eso es RTE05 — esta pantalla no lo insinúa siquiera.
 */

interface TripContextPickerProps {
    busy?: boolean;
    /** Plan de partida, al cambiar de plan sobre un viaje en curso. */
    initial?: TripPlanInput | null;
    confirmLabel: string;
    onCancel?: () => void;
    onConfirm: (plan: TripPlanInput) => void;
}

export function TripContextPicker(props: TripContextPickerProps) {
    const {
        busy, initial, confirmLabel, onCancel, onConfirm,
    } = props;

    const [purpose, setPurpose] = useState<TripPurpose | null>(
        initial?.purpose ?? null,
    );
    const [reference, setReference] = useState(initial?.context_reference ?? '');
    const [valueId, setValueId] = useState<string>(
        initial?.standard_value_id ? String(initial.standard_value_id) : '',
    );
    const [opciones, setOpciones] = useState<StandardValue[]>([]);
    const [cargando, setCargando] = useState(false);

    const contexto = purpose ? TRIP_CONTEXTS[purpose] : null;

    useEffect(() => {
        if (!contexto?.standardList) {
            setOpciones([]);
            return;
        }
        setCargando(true);
        fetchStandardValues(contexto.standardList)
            .then(setOpciones)
            .catch(() => setOpciones([]))
            .finally(() => setCargando(false));
    }, [contexto?.standardList]);

    // El valor de lista es obligatorio donde aplica. El servidor lo exige
    // igualmente; deshabilitar el botón sólo evita ofrecer algo que va a
    // fallar.
    const faltaValor = Boolean(contexto?.standardList) && !valueId;
    const listo = purpose !== null && !faltaValor;

    if (purpose === null) {
        return (
            <div className="flex flex-col gap-3" data-testid="TripContextPicker">
                <p className="text-center text-sm text-muted-foreground">
                    Where are you heading?
                </p>
                {TRIP_PURPOSES.map((codigo) => (
                    <Button
                        key={codigo}
                        variant={codigo === 'home' ? 'secondary' : 'outline'}
                        size="lg"
                        className="h-14 w-full justify-start text-base"
                        disabled={busy}
                        onClick={() => setPurpose(codigo)}
                    >
                        {TRIP_CONTEXTS[codigo].label}
                    </Button>
                ))}
                {onCancel && (
                    <Button variant="ghost" onClick={onCancel} disabled={busy}>
                        Cancel
                    </Button>
                )}
            </div>
        );
    }

    return (
        <div className="flex flex-col gap-4" data-testid="TripContextForm">
            <div className="flex items-center justify-between">
                <p className="text-base font-medium text-foreground">
                    {contexto?.label}
                </p>
                <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={() => { setPurpose(null); setValueId(''); }}
                >
                    Change
                </Button>
            </div>

            {contexto?.standardList && (
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

            {contexto?.freeTextLabel && (
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
                className="h-14 w-full text-lg"
                disabled={busy || !listo}
                onClick={() => onConfirm({
                    purpose,
                    context_reference: reference.trim() || null,
                    standard_value_id: valueId ? Number(valueId) : null,
                })}
            >
                {confirmLabel}
            </Button>

            {onCancel && (
                <Button variant="ghost" onClick={onCancel} disabled={busy}>
                    Cancel
                </Button>
            )}
        </div>
    );
}
