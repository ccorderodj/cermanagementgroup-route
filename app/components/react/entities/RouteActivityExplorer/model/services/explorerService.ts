import { $api, parseApi } from '@/shared/api';
import { explorerViewSchema, type ExplorerRange, type ExplorerView } from '../types';

/**
 * Un nivel del explorador por petición.
 *
 * No se pide el árbol completo: abrir la página no puede traer la historia del
 * tenant, y bajar por una rama no puede traer las demás. El servidor resuelve
 * el periodo y devuelve sus grupos o sus paradas.
 */
export async function fetchExplorer(params: {
    range: ExplorerRange;
    date: string;
    supervisorUserId?: number | null;
}): Promise<ExplorerView> {
    const query: Record<string, string> = {
        range: params.range,
        date: params.date,
    };
    if (params.supervisorUserId != null) {
        query.supervisor_user_id = String(params.supervisorUserId);
    }
    const response = await $api.get('/activity-explorer', { params: query });
    return parseApi(explorerViewSchema, response.data, 'fetchExplorer');
}
