import { z } from 'zod';

/**
 * El viaje del supervisor, tal y como lo sirve la API (RTE04).
 *
 * Los siete contextos los define el producto, no el tenant: un supervisor no
 * inventa motivos de desplazamiento. Por eso son un enum cerrado aquí y un
 * `CHECK` en la base, no una lista configurable.
 */
export const TRIP_PURPOSES = [
    'client_visit',
    'recruiting',
    'employee_visit',
    'check_delivery',
    'office',
    'other',
    'home',
] as const;

export const tripPurposeSchema = z.enum(TRIP_PURPOSES);
export type TripPurpose = z.infer<typeof tripPurposeSchema>;

export const tripStatusSchema = z.enum([
    'planning',
    'in_transit',
    'arrived',
    'closed',
    'interrupted',
]);
export type TripStatus = z.infer<typeof tripStatusSchema>;

export const tripSchema = z.object({
    id: z.number(),
    work_session_id: z.number(),
    sequence: z.number(),
    status: tripStatusSchema,

    // El plan original viaja junto al actual a propósito: hace visible que el
    // plan cambió por el camino sin tener que pedir el historial.
    original_purpose: tripPurposeSchema,
    original_context_reference: z.string().nullable().optional(),
    original_standard_value_id: z.number().nullable().optional(),

    current_purpose: tripPurposeSchema,
    current_context_reference: z.string().nullable().optional(),
    current_standard_value_id: z.number().nullable().optional(),

    started_at: z.string().nullable().optional(),
    arrived_at: z.string().nullable().optional(),
    ended_at: z.string().nullable().optional(),

    version: z.number(),
    created_at: z.string(),
    updated_at: z.string(),
});

export type Trip = z.infer<typeof tripSchema>;

export const tripPurposeChangeSchema = z.object({
    id: z.number(),
    from_purpose: tripPurposeSchema,
    from_context_reference: z.string().nullable().optional(),
    from_standard_value_id: z.number().nullable().optional(),
    to_purpose: tripPurposeSchema,
    to_context_reference: z.string().nullable().optional(),
    to_standard_value_id: z.number().nullable().optional(),
    changed_at: z.string(),
    changed_by: z.number(),
});

export type TripPurposeChange = z.infer<typeof tripPurposeChangeSchema>;

/** Lo que el supervisor decide antes de salir. */
export interface TripPlanInput {
    purpose: TripPurpose;
    context_reference?: string | null;
    standard_value_id?: number | null;
}

/**
 * Cómo se llama cada contexto en pantalla, y qué le pide al supervisor.
 *
 * `freeTextLabel` es el dato de texto libre por decisión de CER — nunca un
 * catálogo. `standardList`, cuando existe, es el valor de lista **obligatorio
 * antes de salir**; sólo tres contextos lo tienen, y los demás eligen lo suyo
 * al llegar, que es RTE05.
 */
export const TRIP_CONTEXTS: Record<TripPurpose, {
    label: string;
    freeTextLabel: string | null;
    standardList: string | null;
    standardLabel: string | null;
}> = {
    client_visit: {
        label: 'Client Visit',
        freeTextLabel: 'Destination',
        standardList: null,
        standardLabel: null,
    },
    recruiting: {
        label: 'Recruiting',
        freeTextLabel: 'Area / Location',
        standardList: null,
        standardLabel: null,
    },
    employee_visit: {
        label: 'Employee Visit',
        freeTextLabel: 'Employee / Reference',
        standardList: 'employee_visit_reasons',
        standardLabel: 'Reason',
    },
    check_delivery: {
        label: 'Check Delivery',
        freeTextLabel: 'Employee / Reference',
        standardList: 'delivery_types',
        standardLabel: 'Delivery type',
    },
    office: {
        label: 'Office',
        freeTextLabel: 'Office',
        standardList: 'office_purposes',
        standardLabel: 'Purpose',
    },
    other: {
        label: 'Other',
        freeTextLabel: 'Area / Location',
        standardList: null,
        standardLabel: null,
    },
    home: {
        label: 'Return Home',
        freeTextLabel: null,
        standardList: null,
        standardLabel: null,
    },
};
