/**
 * Que accion ABRE trabajo nuevo y cual CIERRA lo que ya estaba abierto.
 *
 * Por que esta distincion es el checkpoint entero
 * -----------------------------------------------
 * RTE10-A02 bloquea abrir trabajo nuevo sin permiso de ubicacion, y a la vez
 * exige que una operacion ya abierta se pueda **cerrar con verdad** aunque el
 * permiso se haya perdido a mitad. Sin esa excepcion, revocar el permiso
 * dejaria un viaje en ruta y una jornada abierta para siempre: el supervisor
 * quedaria atrapado y el registro, mintiendo.
 *
 *     abre   -> exige permiso concedido
 *     cierra -> se permite siempre, para no atrapar registros abiertos
 *
 * Por que una lista cerrada y no un prefijo
 * ------------------------------------------
 * Seria tentador deducirlo del nombre -- `start` abre, `arrive` cierra -- y
 * seria fragil: `trip.plan` abre y no se llama `start`, y una accion nueva
 * llamada `trip.resume` no caeria en ninguna regla. §14 pide expresamente no
 * fiarse de los nombres de los botones.
 *
 * Asi que cada accion esta clasificada a mano, y
 * `tests/test_operational_action_matrix.py` cruza esta lista contra las que el
 * codigo encola de verdad: una accion nueva sin clasificar rompe la suite. Es
 * el mismo recurso que `tests/test_public_surface.py` usa con la superficie
 * publica, y por el mismo motivo -- lo que crece solo no se detiene con buenas
 * intenciones.
 */

/** Abren un estado operativo nuevo. Exigen permiso concedido. */
export const ABRE_TRABAJO_NUEVO: readonly string[] = [
    'worksession.start',
    'trip.plan',
    'trip.start',
    'trip.change_plan',
    'activity.start',
];

/**
 * Cierran lo que ya estaba abierto. Se permiten sin permiso.
 *
 * `trip.arrive` incluye la llegada a casa: volver a casa cierra su viaje al
 * llegar, no abre nada.
 */
export const CIERRA_TRABAJO_ABIERTO: readonly string[] = [
    'trip.arrive',
    'activity.complete',
    'activity.leave',
    'worksession.end',
];

/** Toda accion operativa conocida, para la comprobacion de la lista cerrada. */
export const ACCIONES_CONOCIDAS: readonly string[] = [
    ...ABRE_TRABAJO_NUEVO,
    ...CIERRA_TRABAJO_ABIERTO,
];

export function abreTrabajoNuevo(kind: string): boolean {
    return ABRE_TRABAJO_NUEVO.includes(kind);
}

/**
 * El error que recibe la pantalla cuando se intenta abrir trabajo sin permiso.
 *
 * Es un tipo propio y no un `Error` cualquiera porque la pantalla tiene que
 * **distinguirlo**: un fallo de red se reintenta y se queda en la cola; esto no
 * se reintenta nunca, se manda a la persona a conceder el permiso.
 */
export class PermisoDeUbicacionRequerido extends Error {
    readonly kind: string;

    constructor(kind: string) {
        super(
            'CER Route requires location access to start new work. '
            + `The action '${kind}' was not recorded.`,
        );
        this.name = 'PermisoDeUbicacionRequerido';
        this.kind = kind;
    }
}
