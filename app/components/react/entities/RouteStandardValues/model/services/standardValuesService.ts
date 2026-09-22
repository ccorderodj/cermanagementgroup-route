import { z } from 'zod';
import { $api, parseApi } from '@/shared/api';
import {
    standardValueSchema,
    standardValueListSummarySchema,
    type StandardValue,
    type StandardValueListSummary,
} from '../types';

/** Llamadas a la API de listas configurables, validadas con Zod. */

export async function fetchStandardValueLists(): Promise<StandardValueListSummary[]> {
    const response = await $api.get('/standard-values/lists');
    return parseApi(
        z.array(standardValueListSummarySchema),
        response.data,
        'fetchStandardValueLists',
    );
}

/**
 * Valores de una lista. `includeInactive` decide qué pregunta se hace: un
 * administrador necesita ver lo retirado, un formulario operativo no.
 */
export async function fetchStandardValues(
    listCode: string,
    includeInactive = false,
): Promise<StandardValue[]> {
    const response = await $api.get(`/standard-values/${listCode}`, {
        params: { include_inactive: includeInactive },
    });
    return parseApi(z.array(standardValueSchema), response.data, 'fetchStandardValues');
}

export async function createStandardValue(
    listCode: string,
    label: string,
): Promise<StandardValue> {
    const response = await $api.post('/standard-values', {
        list_code: listCode,
        label,
    });
    return parseApi(standardValueSchema, response.data, 'createStandardValue');
}

export async function updateStandardValue(
    valueId: number,
    input: { label?: string; is_active?: boolean; version?: number },
): Promise<StandardValue> {
    const response = await $api.put(`/standard-values/${valueId}`, input);
    return parseApi(standardValueSchema, response.data, 'updateStandardValue');
}

export async function reorderStandardValues(
    listCode: string,
    valueIds: number[],
): Promise<StandardValue[]> {
    const response = await $api.post(`/standard-values/${listCode}/reorder`, {
        value_ids: valueIds,
    });
    return parseApi(z.array(standardValueSchema), response.data, 'reorderStandardValues');
}
