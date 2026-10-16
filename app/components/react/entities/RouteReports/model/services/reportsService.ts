import { $api, parseApi } from '@/shared/api';
import { reportViewSchema, type ReportRange, type ReportView } from '../types';

/**
 * Reports: un periodo para uno o para todos.
 *
 * `date` sólo viaja cuando el usuario **eligió** un periodo concreto, y siempre
 * es el inicio de una opción que dio el servidor. Sin él, el periodo en curso lo
 * decide el servidor con el día de negocio de los supervisores: la pantalla
 * nunca lo calcula con el calendario del navegador.
 *
 * `group` —el inicio de un día, semana o mes del periodo— acota sólo el
 * desglose. El Excel no lo acepta: exporta el periodo principal.
 */
interface ReportQuery {
    range: ReportRange;
    supervisorUserId: number | null;
    date?: string | null;
}

function parametros(params: ReportQuery & { group?: string | null }) {
    const query: Record<string, string> = { range: params.range };
    if (params.supervisorUserId != null) query.supervisor_user_id = String(params.supervisorUserId);
    if (params.date) query.date = params.date;
    if (params.group) query.group = params.group;
    return query;
}

export async function fetchReport(
    params: ReportQuery & { group?: string | null },
): Promise<ReportView> {
    const response = await $api.get('/reports', { params: parametros(params) });
    return parseApi(reportViewSchema, response.data, 'fetchReport');
}

/**
 * Descarga el Excel del periodo principal: mismo rango, mismo periodo, mismo
 * supervisor. Nunca el subgrupo del desglose. El servidor lo genera con las
 * mismas filas que la pantalla; aquí sólo se guarda.
 */
export async function downloadReportExcel(params: ReportQuery): Promise<void> {
    const response = await $api.get('/reports/export', {
        params: parametros({ ...params, group: null }),
        responseType: 'blob',
    });
    const disposicion = String(response.headers['content-disposition'] ?? '');
    const nombre = /filename="([^"]+)"/.exec(disposicion)?.[1] ?? 'CER_Route_Report.xlsx';
    const url = URL.createObjectURL(response.data as Blob);
    const enlace = document.createElement('a');
    enlace.href = url;
    enlace.download = nombre;
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    setTimeout(() => URL.revokeObjectURL(url), 500);
}
