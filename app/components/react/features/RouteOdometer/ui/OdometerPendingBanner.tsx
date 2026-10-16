import type { OdometerStatus } from '@/entities/RouteOdometer';

/**
 * El aviso de que falta la lectura inicial.
 *
 * Es un **aviso**, no una puerta. `Start Work` no es `Start Driving`: abrir la
 * jornada no obliga a fotografiar nada, y forzar un diálogo justo después
 * bloquearía a quien empieza el día con trabajo que no implica conducir. Así
 * que aquí sólo se informa y se ofrece resolverlo; quien impide salir sin
 * evidencia es el servidor, en `Start Trip`.
 *
 * Los tres estados que el supervisor tiene que distinguir se dicen con
 * palabras distintas: falta hacerlo, alguien lo está revisando, o ya está
 * autorizado a teclearlo.
 */

interface OdometerPendingBannerProps {
    status: OdometerStatus;
    onCapture: () => void;
    disabled?: boolean;
}

const MENSAJES: Partial<Record<OdometerStatus, string>> = {
    pending: 'Odometer pending',
    exception_requested: 'Odometer waiting for review',
    exception_approved: 'Odometer ready to enter',
};

const ACCIONES: Partial<Record<OdometerStatus, string>> = {
    pending: 'Capture before first trip',
    exception_requested: 'See status',
    exception_approved: 'Enter the reading',
};

export function OdometerPendingBanner(props: OdometerPendingBannerProps) {
    const { status, onCapture, disabled } = props;

    const mensaje = MENSAJES[status];
    if (!mensaje) return null;

    return (
        <button
            type="button"
            data-testid="OdometerPendingBanner"
            disabled={disabled}
            onClick={onCapture}
            className="flex w-full items-center justify-between gap-3 rounded-lg border border-border bg-muted/40 px-4 py-3 text-left disabled:opacity-60"
        >
            <span className="flex flex-col">
                <span className="text-sm font-medium text-foreground">
                    {mensaje}
                </span>
                <span className="text-xs text-muted-foreground">
                    {ACCIONES[status]}
                </span>
            </span>
            <span aria-hidden className="text-lg text-muted-foreground">
                &rsaquo;
            </span>
        </button>
    );
}

/**
 * La distancia de la jornada, cuando ya se puede afirmar.
 *
 * Nunca muestra un cero de relleno: sin las dos lecturas no hay distancia que
 * enseñar, y el componente no se renderiza. Y se etiqueta como odómetro a
 * propósito — no es el millaje oficial de la ruta, que lo calcula otro dominio.
 */
export function OdometerDistance({ distance }: { distance: number | null }) {
    if (distance === null) return null;
    return (
        <p
            data-testid="OdometerDistance"
            className="text-center text-sm text-muted-foreground"
        >
            {`Odometer distance today: ${distance}`}
        </p>
    );
}
