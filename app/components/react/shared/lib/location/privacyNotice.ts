/**
 * El aviso de ubicación, **una sola vez** (§12, D-08.1).
 *
 * Qué pide la instrucción y qué prohíbe
 * -------------------------------------
 * Pide "a one-time plain-language privacy/location explanation … before the
 * first platform permission request". Y prohíbe, en la misma frase, que se
 * convierta en un mensaje operativo recurrente. Las dos cosas juntas describen
 * exactamente esto: se muestra antes del primer prompt del navegador, y no se
 * vuelve a ver.
 *
 * Por qué `localStorage` y no el servidor
 * ---------------------------------------
 * Porque lo que se recuerda es "este navegador ya mostró el aviso", y eso es
 * un hecho del navegador, no del usuario. El permiso de geolocalización lo
 * concede el navegador y se pierde al cambiar de dispositivo, así que un
 * dispositivo nuevo **debe** volver a explicarlo: guardarlo en el servidor
 * haría que el segundo teléfono pidiera permiso sin decir para qué.
 *
 * Que `localStorage` pueda fallar o venir vacío —ventana privada, datos
 * borrados— tiene la consecuencia correcta: se muestra el aviso otra vez. Es el
 * único lado por el que equivocarse es inocuo.
 */

const CLAVE = 'cer-route-location-notice';

/** Si ya se explicó en este navegador. */
export function locationNoticeSeen(): boolean {
    try {
        return window.localStorage.getItem(CLAVE) === '1';
    } catch {
        // Sin almacenamiento se vuelve a explicar. Repetirlo molesta; no
        // explicarlo nunca incumple D-08.1.
        return false;
    }
}

/** Marca que ya se explicó. */
export function markLocationNoticeSeen(): void {
    try {
        window.localStorage.setItem(CLAVE, '1');
    } catch {
        // Si no se puede recordar, el aviso reaparecerá. Preferible a tragarse
        // un fallo de almacenamiento y dejar de capturar.
    }
}

/**
 * El texto, en lenguaje llano.
 *
 * Dice **cuándo**, **qué** y **para qué**, que es lo que "plain-language
 * explanation" significa aquí. No dice "mejoramos su experiencia" ni ninguna
 * fórmula que no informe de nada. Y dice explícitamente lo que la
 * implementación garantiza: sólo durante la jornada, sólo en esos momentos, y
 * que el trabajo no se detiene si no hay señal.
 */
export const LOCATION_NOTICE = {
    title: 'About location',
    body:
        'CER Route records your location at a few points of your work day — when '
        + 'you start work, start a trip, change a plan, arrive, finish an activity '
        + 'and end work — to calculate the road mileage of each trip.',
    boundaries: [
        'Only while your work day is active. Never before you start or after you end it.',
        'Only at those moments. Your route between them is not tracked.',
        'If there is no signal, your work continues normally.',
    ],
    acknowledge: 'Got it',
} as const;
