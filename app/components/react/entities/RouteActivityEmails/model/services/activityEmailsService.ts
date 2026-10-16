import { z } from 'zod';
import { $api, paginatedSchema, parseApi, type Paginated } from '@/shared/api';
import {
    activityEmailPreviewSchema,
    activityEmailRecipientSchema,
    activityEmailTemplateSchema,
    type ActivityEmailPreview,
    type ActivityEmailRecipient,
    type ActivityEmailTemplate,
    type ActivityEmailType,
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
}): Promise<Paginated<ActivityEmailRecipient>> {
    const response = await $api.get('/activity-emails/recipients', {
        params: { page: params.page, page_size: params.pageSize, q: params.q || undefined },
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
