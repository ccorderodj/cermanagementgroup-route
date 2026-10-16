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
 * Bloquea cuando CER Route **no tiene acceso** a la ubicacion -- porque la
 * persona nego el permiso, o porque la ubicacion del dispositivo esta apagada.
 * No bloquea cuando el GPS no consigue fijar un punto: dentro de una nave, en
 * una zona rural o sin cobertura el trabajo sigue, bajo el modelo de evidencia
 * que ya existe. Son dos condiciones distintas y confundirlas dejaria sin
 * trabajar a quien opera bajo techo.
 *
 * La puerta SIEMPRE aparece sin permiso
 * --------------------------------------
 * Tambien con una jornada abierta. La primera version la ocultaba en ese caso
 * para que se pudiera cerrar lo abierto, y el resultado en campo fue el peor
 * posible: una pantalla normal, con todos sus botones, que fallaban al pulsarlos
 * con un mensaje de error y sin ningun `Enable Location`. §5.1 lo prohibe en
 * una frase: el supervisor no puede ver un estado normal y accionable.
 *
 * Ahora, con una operacion abierta, la puerta va **encima** y debajo quedan
 * solo los controles que cierran lo abierto (§8): llegar, completar la parada,
 * terminar la jornada. Lo que abre trabajo nuevo desaparece de la pantalla
 * -- la pagina lo retira con `soloCierre`-- ademas de estar bloqueado en la
 * cola y en el servidor.
 *
 * Lo que esta puerta NO tiene, a proposito
 * -----------------------------------------
 * * no se puede cerrar;
 * * no hay "continuar sin ubicacion";
 * * no hay boton de "comprobar de nuevo" (§5.1): el permiso se cambia fuera de
 *   la pestana, y al volver la pantalla ya lo sabe por si sola.
 */

interface LocationGateProps {
    /** Lo que se muestra cuando hay permiso, o debajo de la puerta si hay algo abierto. */
    children: React.ReactNode;
    /**
     * Hay una operacion abierta que cerrar. Entonces la puerta va encima y no
     * a pantalla completa, para que el cierre siga siendo posible (§8).
     */
    hayOperacionAbierta?: boolean;
    /** Para que la pagina retire lo que abre trabajo nuevo. */
    onPermisoChange?: (permiso: PermisoOperativo) => void;
}

function Mensaje({
    pidiendo, sinDialogo, onHabilitar, compacto,
}: {
    pidiendo: boolean;
    sinDialogo: boolean;
    onHabilitar: () => void;
    compacto: boolean;
}) {
    return (
        <div
            className={compacto
                ? 'flex flex-col items-center gap-4 rounded-lg border border-border bg-card p-5 text-center'
                : 'flex min-h-[70vh] flex-col items-center justify-center gap-6 p-6 text-center'}
            data-testid="location-gate"
        >
            <div className="space-y-2">
                <h2 className="text-xl font-semibold text-foreground">Location Required</h2>
                <p className="mx-auto max-w-sm text-sm text-muted-foreground">
                    CER Route requires location access to use My Route.
                </p>
                {compacto && (
                    <p className="mx-auto max-w-sm text-sm text-muted-foreground">
                        You can still finish what is already open below. Nothing new
                        can start until location is on.
                    </p>
                )}
            </div>

            <Button
                size="lg"
                className="h-12 w-full max-w-sm"
                disabled={pidiendo}
                onClick={onHabilitar}
            >
                {pidiendo ? 'Waiting for your answer…' : 'Enable Location'}
            </Button>

            {sinDialogo && (
                /* El navegador ya no vuelve a preguntar -- o la ubicacion esta
                   apagada en el propio telefono--, asi que la unica salida
                   honesta es decir donde se cambia. */
                <p className="mx-auto max-w-sm text-xs text-muted-foreground">
                    Location is blocked, so your browser will not ask again. Turn on
                    Location in your phone settings, and allow it for this site from
                    the icon at the left of the address bar. This screen will continue
                    on its own.
                </p>
            )}
        </div>
    );
}

export function LocationGate(props: LocationGateProps) {
    const { children, hayOperacionAbierta = false, onPermisoChange } = props;

    const [permiso, setPermiso] = useState<PermisoOperativo | null>(null);
    const [pidiendo, setPidiendo] = useState(false);
    // El dialogo nativo no se abre si el sitio ya esta denegado, ni si la
    // ubicacion del telefono esta apagada: `getCurrentPosition` falla al
    // instante. Entonces no se simula que se pregunto; se dice donde cambiarlo.
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
            // Partiendo de `prompt`, un `denied` es que la persona dijo que no.
            // Partiendo de cualquier otra cosa es que no hubo dialogo: el sitio
            // ya estaba bloqueado, o la ubicacion del telefono esta apagada.
            if (resultado !== 'granted' && crudo !== 'prompt') setSinDialogo(true);
        } finally {
            setPidiendo(false);
        }
    };

    if (permiso === null) {
        // Mientras no se sabe, no se deja pasar ni se bloquea: mostrar la puerta
        // un instante a quien si tiene acceso seria un parpadeo, y dejar pasar
        // seria abrir lo que esto cierra. Con algo abierto si se muestra debajo:
        // ocultarlo seria impedir cerrarlo mientras se consulta.
        if (hayOperacionAbierta) {
            // eslint-disable-next-line react/jsx-no-useless-fragment
            return <>{children}</>;
        }
        return (
            <div className="flex min-h-[60vh] items-center justify-center p-6">
                <p className="text-sm text-muted-foreground">Checking location access…</p>
            </div>
        );
    }

    if (esOperativo(permiso)) {
        // eslint-disable-next-line react/jsx-no-useless-fragment
        return <>{children}</>;
    }

    if (hayOperacionAbierta) {
        return (
            <div className="flex flex-col gap-4">
                <Mensaje
                    pidiendo={pidiendo}
                    sinDialogo={sinDialogo}
                    onHabilitar={habilitar}
                    compacto
                />
                {children}
            </div>
        );
    }

    return (
        <Mensaje
            pidiendo={pidiendo}
            sinDialogo={sinDialogo}
            onHabilitar={habilitar}
            compacto={false}
        />
    );
}
