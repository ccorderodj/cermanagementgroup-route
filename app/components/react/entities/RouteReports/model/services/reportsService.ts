import { $api, parseApi } from '@/shared/api';
import { reportViewSchema, type ReportRange, type ReportView } from '../types';

/**
 * Reports: el periodo **en curso** para uno o para todos.
 *
 * No se manda ninguna fecha: el V0.7 no navega entre periodos, y el periodo en
 * curso lo decide el servidor con el día de negocio de los supervisores, no el
 * calendario del navegador.
 */
function parametros(range: ReportRange, supervisorUserId: number | null) {
    const query: Record<string, string> = { range };
    if (supervisorUserId != null) query.supervisor_user_id = String(supervisorUserId);
    return query;
}

export async function fetchReport(params: {
    range: ReportRange;
    supervisorUserId: number | null;
}): Promise<ReportView> {
    const response = await $api.get('/reports', {
        params: parametros(params.range, params.supervisorUserId),
    });
    return parseApi(reportViewSchema, response.data, 'fetchReport');
}

/**
 * Descarga el Excel del mismo informe: mismo rango, mismo supervisor. El
 * servidor lo genera con las mismas filas que la pantalla; aquí sólo se guarda.
 */
export async function downloadReportExcel(params: {
    range: ReportRange;
    supervisorUserId: number | null;
}): Promise<void> {
    const response = await $api.get('/reports/export', {
        params: parametros(params.range, params.supervisorUserId),
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
