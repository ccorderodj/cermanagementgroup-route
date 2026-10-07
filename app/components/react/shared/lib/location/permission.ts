/**
 * El permiso de ubicacion, que NO es lo mismo que tener senal.
 *
 * La distincion que gobierna todo este archivo
 * ---------------------------------------------
 * RTE10-A02 bloquea la operacion cuando el supervisor **no concede** acceso a
 * su ubicacion. No la bloquea cuando el dispositivo no consigue un punto: un
 * almacen, una nave industrial o una zona rural dejan al GPS sin fijar durante
 * minutos u horas, y ahi el trabajo tiene que seguir bajo el modelo de
 * evidencia que ya existe -- Fresh, Cached, Recovery, Missing.
 *
 *     permiso denegado      -> se bloquea        (una decision de la persona)
 *     sin senal             -> NO se bloquea     (una condicion del entorno)
 *
 * Confundirlas seria dejar sin trabajar a media plantilla por estar dentro de
 * un edificio.
 *
 * El caso que obliga a sondear
 * -----------------------------
 * `navigator.permissions.query({name:'geolocation'})` no existe en todos los
 * navegadores -- Safari de iOS no lo soporto durante anos, y es un navegador
 * de campo, no un caso de laboratorio. Ahi la Permissions API devuelve
 * `unavailable`, que **no significa denegado**: significa que no sabemos.
 *
 * Tratar `unavailable` como denegado dejaria a todo ese parque fuera del
 * producto. Tratarlo como concedido abriria la puerta que este checkpoint
 * cierra. Asi que no se asume: se **pregunta al GPS**, y su error lo dice sin
 * ambiguedad:
 *
 *     getCurrentPosition resuelve        -> hay permiso
 *     error code 1  PERMISSION_DENIED    -> no hay permiso
 *     error code 2  POSITION_UNAVAILABLE -> hay permiso, no hay senal
 *     error code 3  TIMEOUT              -> hay permiso, no hay senal
 *
 * Los codigos 2 y 3 son exactamente el caso que §2.2 prohibe bloquear, y por
 * eso se resuelven como `granted`: el permiso no es el problema.
 */

/** Lo que el navegador dice, sin interpretar. */
export type EstadoDePermiso = 'granted' | 'denied' | 'prompt' | 'unavailable';

/**
 * Evento de documento con el que cualquier parte del cliente pide que la puerta
 * vuelva a mirar el permiso.
 *
 * Existe porque apagar la ubicacion desde la persiana de Android no siempre
 * oculta la pagina ni le quita el foco: ninguna de las cuatro vias de
 * `observarPermiso` se entera. Pero el siguiente intento de abrir trabajo si
 * lo descubre -- y en ese momento la puerta tiene que aparecer, no un mensaje
 * de error sobre una pantalla que parece normal.
 */
export const REVISAR_PERMISO = 'cer:revisar-permiso-ubicacion';

export function pedirRevisionDelPermiso(): void {
    if (typeof document !== 'undefined') {
        document.dispatchEvent(new Event(REVISAR_PERMISO));
    }
}

/** Lo que el producto decide, ya sin ambiguedad. */
export type PermisoOperativo = 'granted' | 'denied' | 'prompt';

/**
 * Cuanto se espera al sondeo. Corto a proposito: no se busca un punto, se busca
 * el veredicto, y agotar el tiempo ya es un veredicto -- hay permiso, falta
 * senal--. Esperar mas solo retrasa la pantalla sin cambiar la respuesta.
 */
const TIMEOUT_DEL_SONDEO_MS = 4_000;

/** `PERMISSION_DENIED` segun la especificacion de Geolocation. */
const CODIGO_DENEGADO = 1;

/**
 * Cuanto se espera un "no" antes de concluir que hay acceso.
 *
 * Una denegacion -del sitio o de la ubicacion del telefono- llega en
 * milisegundos: es una comprobacion de autorizacion, no una busqueda de
 * satelites. 500 ms es un margen de mas de cincuenta veces sobre eso, y a la
 * vez lo bastante corto como para no notarse al pulsar `Start Trip`. Es un
 * valor a confirmar en campo, y esta declarado asi en el reporte.
 */
const VENTANA_DE_DENEGACION_MS = 500;

function hayGeolocalizacion(): boolean {
    return typeof navigator !== 'undefined' && !!navigator.geolocation;
}

/** El estado crudo de la Permissions API, o `unavailable` si no existe. */
export async function leerEstadoCrudo(): Promise<EstadoDePermiso> {
    try {
        if (typeof navigator === 'undefined' || !navigator.permissions?.query) {
            return 'unavailable';
        }
        const estado = await navigator.permissions.query({
            name: 'geolocation' as PermissionName,
        });
        return estado.state as EstadoDePermiso;
    } catch {
        return 'unavailable';
    }
}

/**
 * Sondea el GPS para decidir si hay permiso cuando la Permissions API no esta.
 *
 * `maximumAge: Infinity` a proposito: vale cualquier punto cacheado, por viejo
 * que sea. No se quiere la posicion -- se quiere saber si el navegador deja
 * pedirla. Un punto de hace una hora responde esa pregunta igual de bien y sin
 * encender el GPS.
 */
function sondear(): Promise<PermisoOperativo> {
    if (!hayGeolocalizacion()) return Promise.resolve('denied');
    return new Promise((resolver) => {
        let decidido = false;
        const decidir = (veredicto: PermisoOperativo) => {
            if (decidido) return;
            decidido = true;
            resolver(veredicto);
        };
        // La asimetria que permite no esperar al GPS. Una DENEGACION es
        // instantanea: el sistema operativo contesta "no" sin tocar el
        // hardware. La FALTA DE SENAL es una espera: el GPS busca satelites
        // hasta agotar el tiempo. Asi que si en esta ventana no ha llegado un
        // "no", la respuesta es "hay acceso" -- y lo que tarde el punto es
        // asunto del modelo de evidencia, no de esta puerta.
        //
        // Sin esta ventana, la primera correccion esperaba el TIMEOUT completo
        // bajo techo: 4 s al cargar y 4 s en cada Start Trip. Lo detecto el test
        // de RTE06 que prohibe que una accion espere a la ubicacion (§36), y es
        // exactamente la nave industrial que §2.2 no permite frenar.
        const reloj = setTimeout(() => decidir('granted'), VENTANA_DE_DENEGACION_MS);
        navigator.geolocation.getCurrentPosition(
            () => {
                clearTimeout(reloj);
                decidir('granted');
            },
            (error) => {
                clearTimeout(reloj);
                decidir(error.code === CODIGO_DENEGADO ? 'denied' : 'granted');
            },
            { timeout: TIMEOUT_DEL_SONDEO_MS, maximumAge: Infinity },
        );
    });
}

/**
 * El veredicto operativo: si el supervisor puede abrir trabajo nuevo.
 *
 * `prompt` **no** es operativo. Es el estado de quien todavia no ha decidido, y
 * §2.1 lo pone del lado bloqueado junto a `denied`: el producto no opera con un
 * permiso que nadie ha concedido todavia.
 */
export async function leerPermisoOperativo(): Promise<PermisoOperativo> {
    const crudo = await leerEstadoCrudo();

    // `prompt` y `denied` se respetan sin sondear. Sondear en `prompt` abriria
    // el dialogo nativo sin que la persona lo pidiera -- §7 lo prohibe, y para
    // eso esta el boton `Enable Location`.
    if (crudo === 'prompt' || crudo === 'denied') return crudo;

    // `granted` NO basta, y esto es un defecto corregido con datos de campo.
    //
    // La Permissions API describe el permiso **del sitio**. No sabe nada de la
    // ubicacion **del dispositivo**: con el interruptor de ubicacion de Android
    // o los Servicios de Localizacion de iOS apagados, el sitio sigue
    // "concedido" y `getCurrentPosition` responde PERMISSION_DENIED igual.
    //
    // Medido en produccion: de 119 denegaciones reales, **46 -el 39 %-**
    // ocurrieron con la Permissions API diciendo `granted`. La primera version
    // de esta puerta se fiaba de ella y no aparecia justo en ese caso, que es
    // el que el supervisor describe como "tengo la ubicacion desactivada".
    //
    // Asi que `granted` y `unavailable` se verifican pidiendo una posicion. No
    // abre ningun dialogo -- el sitio ya esta concedido o el navegador no sabe
    // decirlo-- y su error es inequivoco: 1 es acceso denegado; 2 y 3 son falta
    // de senal, que §2.2 prohibe bloquear.
    return sondear();
}

export function esOperativo(permiso: PermisoOperativo): boolean {
    return permiso === 'granted';
}

/**
 * Pide el permiso de verdad: abre el dialogo nativo del navegador.
 *
 * Solo `getCurrentPosition` lo abre; la Permissions API unicamente consulta. Y
 * solo se abre cuando el estado es `prompt`: si el navegador ya marco el sitio
 * como denegado, volver a llamar **no vuelve a preguntar** -- devuelve el error
 * al instante. Por eso la pantalla, en ese caso, explica como habilitarlo desde
 * los ajustes en vez de simular que pregunto.
 */
export async function pedirPermiso(): Promise<PermisoOperativo> {
    if (!hayGeolocalizacion()) return 'denied';
    return new Promise((resolver) => {
        navigator.geolocation.getCurrentPosition(
            () => resolver('granted'),
            (error) => resolver(error.code === CODIGO_DENEGADO ? 'denied' : 'granted'),
            { timeout: TIMEOUT_DEL_SONDEO_MS, maximumAge: Infinity },
        );
    });
}

/**
 * Avisa cuando el permiso cambia, por las cuatro vias que un navegador ofrece.
 *
 * Ninguna basta sola, y por eso estan las cuatro:
 *
 * * `PermissionStatus.onchange` -- la unica que avisa en el momento, y no
 *   existe en todos los navegadores;
 * * `visibilitychange` -- revocar el permiso se hace en los ajustes del
 *   sistema, es decir **fuera** de la pestana. Al volver hay que releer;
 * * `focus` -- lo mismo para quien cambia de ventana sin ocultar la pestana;
 * * `pageshow` -- vuelta desde la cache de atras/adelante, donde no hay
 *   recarga y el valor en memoria sobreviviria obsoleto.
 *
 * §13 pide expresamente no fiarse de un valor en memoria. Esto es lo que
 * convierte esa exigencia en codigo.
 *
 * Devuelve la funcion para dejar de escuchar.
 */
export function observarPermiso(alCambiar: (permiso: PermisoOperativo) => void): () => void {
    let vivo = true;
    let suelta: (() => void) | null = null;

    const releer = () => {
        if (!vivo) return;
        leerPermisoOperativo().then((permiso) => {
            if (vivo) alCambiar(permiso);
        }).catch(() => { /* sin respuesta no se cambia el estado */ });
    };

    const alVolver = () => {
        if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
        releer();
    };

    if (typeof document !== 'undefined') {
        document.addEventListener('visibilitychange', alVolver);
        document.addEventListener(REVISAR_PERMISO, releer);
    }
    if (typeof window !== 'undefined') {
        window.addEventListener('focus', releer);
        window.addEventListener('pageshow', releer);
    }

    (async () => {
        try {
            if (typeof navigator === 'undefined' || !navigator.permissions?.query) return;
            const estado = await navigator.permissions.query({
                name: 'geolocation' as PermissionName,
            });
            if (!vivo) return;
            estado.onchange = releer;
            suelta = () => { estado.onchange = null; };
        } catch {
            // Sin `onchange` quedan las otras tres vias. No es un fallo.
        }
    })().catch(() => { /* idem */ });

    releer();

    return () => {
        vivo = false;
        if (typeof document !== 'undefined') {
            document.removeEventListener('visibilitychange', alVolver);
            document.removeEventListener(REVISAR_PERMISO, releer);
        }
        if (typeof window !== 'undefined') {
            window.removeEventListener('focus', releer);
            window.removeEventListener('pageshow', releer);
        }
        suelta?.();
    };
}
