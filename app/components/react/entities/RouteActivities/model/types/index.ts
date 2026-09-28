import { z } from 'zod';
import { type TripPurpose } from '@/entities/RouteTrips';

/**
 * El bloque de trabajo de una parada (RTE05).
 *
 * Un bloque, no un cronómetro por actividad
 * ------------------------------------------
 * Quien atiende a un cliente puede revisar el servicio, seguir una incidencia de
 * asistencia y hablar de seguridad **en la misma visita**. Eso es una parada con
 * tres etiquetas, no tres paradas: un inicio, un fin, una duración, un resultado
 * y una nota. Las actividades seleccionadas describen el bloque; no lo dividen.
 */

export const activityExecutionStatusSchema = z.enum([
    'in_progress',
    'completed',
    'left',
]);
export type ActivityExecutionStatus = z.infer<typeof activityExecutionStatusSchema>;

export const terminalActionSchema = z.enum(['complete', 'leave']);
export type TerminalAction = z.infer<typeof terminalActionSchema>;

export const selectedActivitySchema = z.object({
    standard_value_id: z.number(),
    /** La etiqueta **de entonces**: el histórico se lee como era. */
    label: z.string(),
    sort_order: z.number(),
});
export type SelectedActivity = z.infer<typeof selectedActivitySchema>;

export const activityExecutionSchema = z.object({
    id: z.number(),
    work_session_id: z.number(),
    trip_id: z.number(),
    status: activityExecutionStatusSchema,
    terminal_action: terminalActionSchema.nullable().optional(),

    started_at: z.string(),
    started_received_at: z.string(),
    started_at_source: z.enum(['device', 'server_receipt']),
    ended_at: z.string().nullable().optional(),

    outcome_standard_value_id: z.number().nullable().optional(),
    outcome_label: z.string().nullable().optional(),
    received_by_standard_value_id: z.number().nullable().optional(),
    received_by_label: z.string().nullable().optional(),
    notes: z.string().nullable().optional(),

    activities: z.array(selectedActivitySchema).default([]),
    version: z.number(),
});
export type ActivityExecution = z.infer<typeof activityExecutionSchema>;

/**
 * Qué pide cada contexto **al llegar**.
 *
 * Sólo tres seleccionan actividad. Employee Visit y Office ya trajeron su dato
 * desde la planificación —el motivo y el propósito—, y añadirles un selector
 * aquí sería preguntar dos veces lo mismo para que todas las pantallas se
 * parezcan. HOME no aparece: su viaje se cerró al llegar.
 *
 * El servidor comprueba lo mismo, así que esto es sólo qué enseñar.
 */
export const POSTARRIVAL_ACTIVITY_LIST: Partial<Record<TripPurpose, string>> = {
    client_visit: 'client_visit_activities',
    recruiting: 'recruiting_activities',
    other: 'other_activities',
};

/** La lista de resultados. La misma para todos los contextos. */
export const OUTCOME_LIST = 'outcomes';

/** Quién recibió la entrega. Sólo Check Delivery, y allí obligatorio. */
export const RECEIVED_BY_LIST = 'received_by';

/** Si ese contexto exige elegir al menos una actividad antes de empezar. */
export const requiereActividades = (purpose: TripPurpose): boolean => (
    POSTARRIVAL_ACTIVITY_LIST[purpose] !== undefined
);

/** Si ese contexto exige registrar quién recibió antes de terminar. */
export const requiereReceptor = (purpose: TripPurpose): boolean => (
    purpose === 'check_delivery'
);
