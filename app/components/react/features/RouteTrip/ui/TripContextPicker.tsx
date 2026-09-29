import { useState } from 'react';
import { Button } from '@/shared/ui/shadcn/new-york';
import { type TripPlanInput, type TripPurpose } from '@/entities/RouteTrips';
import { TripContextChoices } from './TripContextChoices';
import { TripContextForm } from './TripContextForm';

/**
 * Elegir contexto y completar sus datos, en dos pasos.
 *
 * Lo usa **`Change Plan`**, que es el caso en el que hace falta volver a elegir
 * el destino estando ya en ruta. El workbench no lo usa: allí las siete
 * opciones son la pantalla de reposo, no un paso dentro de otra cosa, y por eso
 * monta `TripContextChoices` directamente.
 *
 * Las dos rutas comparten los mismos dos componentes, así que ven las mismas
 * siete opciones con la misma presentación. Eso es lo que PD-07 pide: cambiar
 * de plan no estrena una taxonomía propia.
 */

interface TripContextPickerProps {
    busy?: boolean;
    /** Plan de partida del viaje que se está cambiando. */
    initial?: TripPlanInput | null;
    confirmLabel: string;
    onCancel: () => void;
    onConfirm: (plan: TripPlanInput) => void;
}

export function TripContextPicker(props: TripContextPickerProps) {
    const { busy, initial, confirmLabel, onCancel, onConfirm } = props;
    // Arranca **sin** contexto elegido, aunque el viaje ya tenga uno: cambiar
    // de plan empieza por volver a ver las siete opciones (PD-07). Sembrarlo
    // con el propósito actual saltaba directo al formulario, y entonces
    // `Change Plan` no enseñaba las opciones que debía reutilizar.
    const [purpose, setPurpose] = useState<TripPurpose | null>(null);

    if (purpose === null) {
        return (
            <div className="flex flex-col gap-3" data-testid="TripContextPicker">
                <p className="text-center text-sm text-muted-foreground">
                    Where are you heading?
                </p>
                <TripContextChoices busy={busy} onSelect={setPurpose} />
                <Button variant="ghost" onClick={onCancel} disabled={busy}>
                    Cancel
                </Button>
            </div>
        );
    }

    return (
        <TripContextForm
            purpose={purpose}
            busy={busy}
            initial={initial?.purpose === purpose ? initial : null}
            confirmLabel={confirmLabel}
            backLabel="Change"
            onBack={() => setPurpose(null)}
            onConfirm={onConfirm}
        />
    );
}
