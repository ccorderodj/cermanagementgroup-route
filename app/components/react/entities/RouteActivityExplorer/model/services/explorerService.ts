import { $api, parseApi } from '@/shared/api';
import {
    explorerViewSchema,
    tripMapSchema,
    type ExplorerRange,
    type ExplorerView,
    type TripMap,
} from '../types';

/**
 * Un nivel del explorador por petición.
 *
 * No se pide el árbol completo: abrir la página no puede traer la historia del
 * tenant, y bajar por una rama no puede traer las demás. El servidor resuelve
 * el periodo y devuelve sus grupos o sus paradas.
 */
export async function fetchExplorer(params: {
    range: ExplorerRange;
    /**
     * El dia ancla. `null` significa "no lo se todavia": el servidor resuelve
     * el dia de negocio de la compania y lo devuelve en `start`. La pantalla
     * **no** puede suplirlo con la fecha del navegador, porque el calendario
     * del dispositivo y el dia de negocio del tenant no son el mismo dato.
     */
    date: string | null;
    supervisorUserId?: number | null;
}): Promise<ExplorerView> {
    const query: Record<string, string> = {
        range: params.range,
    };
    if (params.date) {
        query.date = params.date;
    }
    if (params.supervisorUserId != null) {
        query.supervisor_user_id = String(params.supervisorUserId);
    }
    const response = await $api.get('/activity-explorer', { params: query });
    return parseApi(explorerViewSchema, response.data, 'fetchExplorer');
}

/**
 * La actividad **propia** (RTE08 personal, `/route/activity`).
 *
 * No hay parámetro de persona: el servidor toma el usuario de la sesión y el
 * tenant del subdominio. Mismo contrato y mismos números que `fetchExplorer`
 * para esa persona; `supervisors` llega vacío.
 */
export async function fetchMyActivity(params: {
    range: ExplorerRange;
    /** Como en `fetchExplorer`: `null` deja el día de negocio al servidor. */
    date: string | null;
}): Promise<ExplorerView> {
    const query: Record<string, string> = { range: params.range };
    if (params.date) {
        query.date = params.date;
    }
    const response = await $api.get('/activity-explorer/me', { params: query });
    return parseApi(explorerViewSchema, response.data, 'fetchMyActivity');
}

/**
 * Los puntos del cálculo de millas de **un** viaje, sólo al abrir su visor.
 * El servidor exige el permiso del mapa y que el viaje esté en el alcance.
 */
export async function fetchTripMap(tripId: number): Promise<TripMap> {
    const response = await $api.get(`/activity-explorer/trips/${tripId}/map`);
    return parseApi(tripMapSchema, response.data, 'fetchTripMap');
}
