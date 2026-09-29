import { TRIP_CONTEXTS, TRIP_PURPOSES, type TripPurpose } from '@/entities/RouteTrips';

/**
 * Las siete opciones aprobadas, en **un solo sitio** y con la presentación
 * aprobada.
 *
 * De dónde sale esta forma
 * ------------------------
 * Del mockup V0.7 aprobado —`04_Mockup_Reference_V0_7/standalone.html`, función
 * `purposeGrid()`—, que es la fuente visual autoritativa. Allí las siete
 * opciones son una **rejilla de dos columnas de tarjetas**, cada una con su
 * nombre y una segunda línea que lo sitúa, no botones apilados a todo el ancho.
 *
 * El mockup describe la forma con colores fijos; aquí se expresa con los tokens
 * del sistema. Es la única traducción que se hace, y es obligatoria: un
 * `#e1e6ec` escrito a mano no responde a la marca del tenant, que es
 * precisamente el defecto que ya se corrigió una vez en el lateral.
 *
 * Una rejilla, dos pantallas
 * --------------------------
 * En el mockup, `purposeGrid()` alimenta el workbench **y** `Change activity`.
 * Aquí igual: un solo componente, así que no pueden divergir en dos taxonomías.
 * Ese es el motivo de que exista, más que ahorrar código.
 *
 * `Home` no se distingue visualmente del resto: en el mockup las siete tarjetas
 * son iguales. Lo que lo diferencia es lo que ocurre al elegirlo, no su aspecto.
 */

interface TripContextChoicesProps {
    busy?: boolean;
    /** El contexto ya elegido, si lo hay. Se marca, como en el mockup. */
    selected?: TripPurpose | null;
    onSelect: (purpose: TripPurpose) => void;
}

export function TripContextChoices(props: TripContextChoicesProps) {
    const { busy, selected = null, onSelect } = props;

    return (
        // Dos columnas en el teléfono, que es el ancho para el que se diseñó;
        // en pantallas anchas la rejilla crece sin dejar de ser la misma.
        <div
            data-testid="TripContextChoices"
            className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4"
        >
            {TRIP_PURPOSES.map((codigo) => {
                const contexto = TRIP_CONTEXTS[codigo];
                const activa = selected === codigo;
                return (
                    <button
                        key={codigo}
                        type="button"
                        disabled={busy}
                        onClick={() => onSelect(codigo)}
                        className={[
                            // `min-h-[72px]` es la altura del mockup, y también
                            // lo que hace que la tarjeta sea un objetivo táctil
                            // cómodo con el teléfono en la mano.
                            'flex min-h-[72px] flex-col justify-center rounded-xl border p-3 text-left',
                            'transition-colors disabled:opacity-60',
                            activa
                                ? 'border-primary bg-accent'
                                : 'border-border bg-card hover:bg-accent/40',
                        ].join(' ')}
                    >
                        <span className="text-sm font-semibold leading-tight text-foreground">
                            {contexto.label}
                        </span>
                        <span className="mt-1 text-xs leading-tight text-muted-foreground">
                            {contexto.hint}
                        </span>
                    </button>
                );
            })}
        </div>
    );
}
