import { z } from 'zod';

/**
 * Las ocho listas aprobadas por CER. **Cerradas**: las define el producto.
 *
 * Lo que es del tenant son los *valores* de dentro, que son filas. Outcome está
 * aquí como código de lista, no como enum de valores: sus opciones
 * ("Completed", "Follow-up Required"…) son datos configurables, tal y como
 * fijó la decisión A-3 del cierre de RTE01.
 */
export const STANDARD_VALUE_LISTS = [
    'client_visit_activities',
    'recruiting_activities',
    'employee_visit_reasons',
    'delivery_types',
    'office_purposes',
    'other_activities',
    'outcomes',
    'received_by',
] as const;

export const standardValueListSchema = z.enum(STANDARD_VALUE_LISTS);
export type StandardValueListCode = z.infer<typeof standardValueListSchema>;

export const standardValueSchema = z.object({
    id: z.number(),
    list_code: z.string(),
    label: z.string(),
    sort_order: z.number(),
    is_active: z.boolean(),
    version: z.number(),
    created_at: z.string(),
    updated_at: z.string(),
});

export type StandardValue = z.infer<typeof standardValueSchema>;

/** Una lista con cuántos valores activos tiene, para el índice de la pantalla. */
export const standardValueListSummarySchema = z.object({
    code: z.string(),
    label: z.string(),
    active_values: z.number(),
});

export type StandardValueListSummary = z.infer<typeof standardValueListSummarySchema>;
