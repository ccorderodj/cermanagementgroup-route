import { z } from 'zod';
import { $api, paginatedSchema, parseApi, type Paginated } from '@/shared/api';
import {
    activityEmailPreviewSchema,
    activityEmailRecipientSchema,
    activityEmailTemplateSchema,
    activityEmailTestResultSchema,
    activityEmailTestTargetsSchema,
    strategicRecipientSchema,
    deliverySchema,
    realReportPreviewSchema,
    reportSendResultSchema,
    resendResultSchema,
    deliveryHistorySchema,
    operationalStatusSchema,
    type ActivityEmailPreview,
    type ActivityEmailRecipient,
    type ActivityEmailTemplate,
    type ActivityEmailTestResult,
    type ActivityEmailTestTargets,
    type ActivityEmailType,
    type StrategicRecipient,
    type Delivery,
    type RealReportPreview,
    type ReportSendResult,
    type ResendResult,
    type DeliveryHistory,
    type DeliveryTrigger,
    type OperationalStatus,
} from '../types';

/**
 * Configuración de los correos de actividad (RTE-NOT-01), validada con Zod.
 *
 * Nada de aquí envía un correo: guardar, activar y previsualizar sólo
 * configuran. El envío es un checkpoint posterior.
 */

export async function fetchActivityEmailTemplates(): Promise<ActivityEmailTemplate[]> {
    const response = await $api.get('/activity-emails/templates');
    return parseApi(z.array(activityEmailTemplateSchema), response.data, 'fetchActivityEmailTemplates');
}

export async function updateActivityEmailTemplate(
    type: ActivityEmailType,
    input: { subject: string; body: string; version: number },
): Promise<ActivityEmailTemplate> {
    const response = await $api.put(`/activity-emails/templates/${type}`, input);
    return parseApi(activityEmailTemplateSchema, response.data, 'updateActivityEmailTemplate');
}

export async function restoreActivityEmailTemplate(
    type: ActivityEmailType,
    version: number,
): Promise<ActivityEmailTemplate> {
    const response = await $api.post(`/activity-emails/templates/${type}/restore-default`, { version });
    return parseApi(activityEmailTemplateSchema, response.data, 'restoreActivityEmailTemplate');
}

export async function previewActivityEmailTemplate(
    type: ActivityEmailType,
    input: { subject: string; body: string },
): Promise<ActivityEmailPreview> {
    const response = await $api.post(`/activity-emails/templates/${type}/preview`, input);
    return parseApi(activityEmailPreviewSchema, response.data, 'previewActivityEmailTemplate');
}

export async function fetchActivityEmailRecipients(params: {
    page: number;
    pageSize: number;
    q?: string;
    /** Sólo «Generate report»: incluye a quien llama para pedir su propio reporte. */
    includeSelf?: boolean;
}): Promise<Paginated<ActivityEmailRecipient>> {
    const response = await $api.get('/activity-emails/recipients', {
        params: {
            page: params.page,
            page_size: params.pageSize,
            q: params.q || undefined,
            include_self: params.includeSelf || undefined,
        },
    });
    return parseApi(
        paginatedSchema(activityEmailRecipientSchema),
        response.data,
        'fetchActivityEmailRecipients',
    );
}

export async function updateActivityEmailRecipient(
    userId: number,
    input: { midday_enabled?: boolean; end_of_day_enabled?: boolean; version: number },
): Promise<ActivityEmailRecipient> {
    const response = await $api.put(`/activity-emails/recipients/${userId}`, input);
    return parseApi(activityEmailRecipientSchema, response.data, 'updateActivityEmailRecipient');
}

export async function fetchActivityEmailTestTargets(): Promise<ActivityEmailTestTargets> {
    const response = await $api.get('/activity-emails/test-targets');
    return parseApi(activityEmailTestTargetsSchema, response.data, 'fetchActivityEmailTestTargets');
}

/** Prueba controlada: datos ficticios, a un destinatario de prueba autorizado. */
export async function sendActivityEmailTest(
    type: ActivityEmailType,
    to: string,
): Promise<ActivityEmailTestResult> {
    const response = await $api.post(`/activity-emails/templates/${type}/test-send`, { to });
    return parseApi(activityEmailTestResultSchema, response.data, 'sendActivityEmailTest');
}

export async function fetchStrategicRecipients(params: {
    page: number;
    pageSize: number;
    q?: string;
    /** Sólo «Generate report»: incluye a quien llama para pedir su propio reporte. */
    includeSelf?: boolean;
}): Promise<Paginated<StrategicRecipient>> {
    const response = await $api.get('/activity-emails/strategic-recipients', {
        params: {
            page: params.page,
            page_size: params.pageSize,
            q: params.q || undefined,
            include_self: params.includeSelf || undefined,
        },
    });
    return parseApi(paginatedSchema(strategicRecipientSchema), response.data, 'fetchStrategicRecipients');
}

export async function updateStrategicRecipient(
    userId: number,
    input: { strategic_midday_enabled?: boolean; strategic_end_of_day_enabled?: boolean; version: number },
): Promise<StrategicRecipient> {
    const response = await $api.put(`/activity-emails/strategic-recipients/${userId}`, input);
    return parseApi(strategicRecipientSchema, response.data, 'updateStrategicRecipient');
}

export interface RealReportRequest {
    report_type: ActivityEmailType;
    recipient_user_id: number;
    operational_date: string;
}

/** Reporte con datos reales, sin enviar (RTE-MAIL-CP4-02). */
export async function previewRealReport(input: RealReportRequest): Promise<RealReportPreview> {
    const response = await $api.post('/activity-emails/reports/preview', input);
    return parseApi(realReportPreviewSchema, response.data, 'previewRealReport');
}

/** Envía ya un reporte que tocaba, a su destinatario configurado. */
export async function sendRealReport(
    input: RealReportRequest & { reason?: string },
): Promise<ReportSendResult> {
    const response = await $api.post('/activity-emails/reports/send', input);
    return parseApi(reportSendResultSchema, response.data, 'sendRealReport');
}

/** Reenvía un reporte que ya salió. `expected_resends`: los reenvíos que se ven ahora. */
export async function resendRealReport(
    input: RealReportRequest & { expected_resends: number; reason?: string },
): Promise<ResendResult> {
    const response = await $api.post('/activity-emails/reports/resend', input);
    return parseApi(resendResultSchema, response.data, 'resendRealReport');
}

/** Proveedor, interruptores, tipos activos y última pasada de cada reloj. */
export async function fetchOperationalStatus(): Promise<OperationalStatus> {
    const response = await $api.get('/activity-emails/status');
    return parseApi(operationalStatusSchema, response.data, 'fetchOperationalStatus');
}

export async function fetchDeliveryHistory(params: {
    page: number;
    pageSize: number;
    dateFrom?: string;
    dateTo?: string;
    reportType?: ActivityEmailType;
    trigger?: DeliveryTrigger;
}): Promise<Paginated<DeliveryHistory>> {
    const response = await $api.get('/activity-emails/history', {
        params: {
            page: params.page,
            page_size: params.pageSize,
            date_from: params.dateFrom || undefined,
            date_to: params.dateTo || undefined,
            report_type: params.reportType || undefined,
            trigger: params.trigger || undefined,
        },
    });
    return parseApi(paginatedSchema(deliveryHistorySchema), response.data, 'fetchDeliveryHistory');
}

export async function fetchDeliveries(params: {
    report_type?: ActivityEmailType;
    recipient_user_id?: number;
    operational_date?: string;
}): Promise<Delivery[]> {
    const response = await $api.get('/activity-emails/reports/deliveries', { params });
    return parseApi(z.array(deliverySchema), response.data, 'fetchDeliveries');
}
