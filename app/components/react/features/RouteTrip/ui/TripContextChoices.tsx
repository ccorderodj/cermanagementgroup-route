import { Button } from '@/shared/ui/shadcn/new-york';
import { TRIP_CONTEXTS, TRIP_PURPOSES, type TripPurpose } from '@/entities/RouteTrips';

/**
 * Las siete opciones aprobadas, en **un solo sitio**.
 *
 * Las pinta el workbench —`What's next?`, el estado de reposo de una jornada
 * activa— y las vuelve a pintar `Change Plan`. Que sean el mismo componente no
 * es ahorro de código: es la garantía de que no aparezca una segunda taxonomía.
 * Dos listas de destinos divergen en cuanto alguien añada un contexto a una y
 * se olvide de la otra, y entonces el supervisor ve opciones distintas según
 * por dónde haya entrado.
 *
 * `Home` va al final y con otro peso visual: volver a casa cierra el día, no
 * abre trabajo.
 */

interface TripContextChoicesProps {
    busy?: boolean;
    onSelect: (purpose: TripPurpose) => void;
}

export function TripContextChoices({ busy, onSelect }: TripContextChoicesProps) {
    return (
        <div className="flex flex-col gap-3" data-testid="TripContextChoices">
            {TRIP_PURPOSES.map((codigo) => (
                <Button
                    key={codigo}
                    variant={codigo === 'home' ? 'secondary' : 'outline'}
                    size="lg"
                    className="h-14 w-full justify-start text-base"
                    disabled={busy}
                    onClick={() => onSelect(codigo)}
                >
                    {TRIP_CONTEXTS[codigo].label}
                </Button>
            ))}
        </div>
    );
}
