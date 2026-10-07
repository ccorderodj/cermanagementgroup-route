import { useEffect, useRef, useState } from 'react';
import { Button } from '@/shared/ui/shadcn/new-york';
import {
    esOperativo, leerEstadoCrudo, observarPermiso, pedirPermiso,
    type PermisoOperativo,
} from '@/shared/lib/location';

/**
 * La puerta de ubicacion de My Route (RTE10-A02).
 *
 * Que bloquea, y que no
 * ---------------------
 * Bloquea cuando el supervisor **no concede** acceso a su ubicacion. No
 * bloquea cuando el GPS no consigue fijar un punto: dentro de una nave, en una
 * zona rural o sin cobertura el trabajo sigue, bajo el modelo de evidencia que
 * ya existe. Son dos condiciones distintas y confundirlas dejaria sin trabajar
 * a quien opera bajo techo.
 *
 * Lo que esta puerta NO tiene, a proposito
 * -----------------------------------------
 * * no se puede cerrar;
 * * no hay "continuar sin ubicacion";
 * * no hay boton de "comprobar de nuevo".
 *
 * Lo ultimo es una exigencia explicita de §5.1, y tiene su motivo: un boton de
 * reintentar traslada a la persona el trabajo de vigilar, y se equivoca justo
 * cuando importa -- el permiso se concede en los ajustes del sistema, fuera de
 * la pestana, y al volver la pantalla ya deberia saberlo. `observarPermiso` lo
 * detecta por cuatro vias y la puerta desaparece sola.
 */

interface LocationGateProps {
    /** Lo que se muestra cuando hay permiso. */
    children: React.ReactNode;
    /**
     * Se deja pasar aunque no haya permiso, para cerrar lo que ya esta abierto
     * (§8). Sin esto, revocar el permiso a mitad de un viaje lo dejaria abierto
     * para siempre y el registro mentiria.
     */
    hayOperacionAbierta?: boolean;
    /** Para avisar al resto de la pantalla de que el permiso cambio. */
    onPermisoChange?: (permiso: PermisoOperativo) => void;
}

export function LocationGate(props: LocationGateProps) {
    const { children, hayOperacionAbierta = false, onPermisoChange } = props;

    const [permiso, setPermiso] = useState<PermisoOperativo | null>(null);
    const [pidiendo, setPidiendo] = useState(false);
    // Si el navegador ya marco el sitio como denegado, `getCurrentPosition` no
    // vuelve a preguntar: devuelve el error al instante. Entonces no se puede
    // simular que se pregunto, hay que explicar donde se cambia.
    const [sinDialogo, setSinDialogo] = useState(false);
    const avisar = useRef(onPermisoChange);
    avisar.current = onPermisoChange;

    useEffect(() => observarPermiso((actual) => {
        setPermiso(actual);
        avisar.current?.(actual);
        if (actual === 'granted') setSinDialogo(false);
    }), []);

    const habilitar = async () => {
        setPidiendo(true);
        try {
            const crudo = await leerEstadoCrudo();
            const resultado = await pedirPermiso();
            setPermiso(resultado);
            avisar.current?.(resultado);
            // `denied` partiendo de `denied` significa que el dialogo no llego
            // a abrirse. Partiendo de `prompt`, que la persona dijo que no.
            if (resultado !== 'granted' && crudo === 'denied') setSinDialogo(true);
        } finally {
            setPidiendo(false);
        }
    };

    // Mientras no se sabe no se bloquea ni se deja pasar: enseñar la puerta
    // durante un instante a quien si tiene permiso seria un parpadeo feo, y
    // dejar pasar seria abrir justo lo que esto cierra.
    if (permiso === null) {
        return (
            <div className="flex min-h-[60vh] items-center justify-center p-6">
                <p className="text-sm text-muted-foreground">Checking location access…</p>
            </div>
        );
    }

    if (esOperativo(permiso) || hayOperacionAbierta) {
        // eslint-disable-next-line react/jsx-no-useless-fragment
        return <>{children}</>;
    }

    return (
        <div
            className="flex min-h-[70vh] flex-col items-center justify-center gap-6 p-6 text-center"
            data-testid="location-gate"
        >
            <div className="space-y-2">
                <h2 className="text-xl font-semibold text-foreground">Location Required</h2>
                <p className="mx-auto max-w-sm text-sm text-muted-foreground">
                    CER Route requires location access to use My Route.
                </p>
            </div>

            <Button
                size="lg"
                className="h-12 w-full max-w-sm"
                disabled={pidiendo}
                onClick={habilitar}
            >
                {pidiendo ? 'Waiting for your answer…' : 'Enable Location'}
            </Button>

            {sinDialogo && (
                /* El navegador ya no vuelve a preguntar, asi que la unica salida
                   honesta es decir donde se cambia. No se promete nada que la
                   plataforma no pueda hacer. */
                <p className="mx-auto max-w-sm text-xs text-muted-foreground">
                    Your browser has blocked location for this site, so it will not
                    ask again. Open the site settings — the icon at the left of the
                    address bar — allow Location, and this screen will continue on
                    its own.
                </p>
            )}
        </div>
    );
}
