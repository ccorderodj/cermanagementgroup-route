import { $api } from '@/shared/api';
import { flushQueue, type FlushResult, type PendingAction } from './offlineQueue';

/**
 * El vaciado de la cola. **Uno**, no uno por dominio.
 *
 * `offlineQueue.ts` sigue sin saber qué es HTTP: recibe el emisor y se ocupa
 * del orden y de la durabilidad. Aquí está el emisor, y está aquí —en `shared`
 * y no dentro de una entidad— porque la cola es una sola. Cuando la Jornada la
 * vaciaba por su cuenta y la Parada quiso enviar lo suyo, la única forma de
 * reutilizar ese emisor era que una entidad importara a la otra, y esas dos ya
 * se referencian en sentido contrario: el ciclo dejaba un esquema de Zod a
 * medio construir en tiempo de carga.
 *
 * `Idempotency-Key` es el identificador de la propia acción, así que reenviarla
 * tras un corte no repite la escritura.
 */
export async function flushPendingActions(): Promise<FlushResult> {
    return flushQueue(async (accion: PendingAction) => {
        await $api.request({
            url: accion.endpoint,
            method: accion.method,
            data: accion.payload,
            headers: { 'Idempotency-Key': accion.id },
        });
    });
}

/**
 * Envía una acción recién encolada y devuelve su rechazo, si el servidor la
 * rechazó **a ella**.
 *
 * Distinguir de quién es el rechazo importa: el vaciado se detiene en la
 * primera que falla, así que un 409 puede pertenecer a algo encolado antes.
 * Atribuirlo a la acción actual mostraría al supervisor un error que no es el
 * suyo sobre una acción que sigue pendiente.
 */
export async function submitAction(accion: PendingAction): Promise<void> {
    const resultado = await flushPendingActions();
    if (resultado.rejected?.id === accion.id) {
        throw resultado.rejectedError;
    }
}
