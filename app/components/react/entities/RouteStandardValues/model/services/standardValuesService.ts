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

/**
 * Saca el valor de la administración. **No** es `updateStandardValue({is_active:
 * false})`: eso lo retira del uso dejándolo visible entre los inactivos, y esto
 * lo quita también de ahí. La fila permanece en el servidor para que la
 * historia siga siendo interpretable.
 */
export async function deleteStandardValue(
    valueId: number,
    version?: number,
): Promise<void> {
    await $api.delete(`/standard-values/${valueId}`, {
        params: version === undefined ? undefined : { version },
    });
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
