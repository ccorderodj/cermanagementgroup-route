import { z } from 'zod';

/** La Jornada, tal y como la sirve `GET /worksessions/current`. */
export const workSessionSchema = z.object({
    id: z.number(),
    status: z.enum(['active', 'ended']),
    session_date: z.string(),
    started_at: z.string(),
    ended_at: z.string().nullable().optional(),
    vehicle_id: z.number().nullable().optional(),
    mpg_snapshot: z.union([z.string(), z.number()]).nullable().optional(),
    version: z.number(),
    created_at: z.string(),
    updated_at: z.string(),
});

export type WorkSession = z.infer<typeof workSessionSchema>;

/**
 * El sobre de `GET /worksessions/current`.
 *
 * Diseñado para crecer: RTE04 añadirá `current_trip` a este mismo tipo, no un
 * segundo endpoint de estado. Aquí solo se declara lo que RTE03 entrega.
 */
export const currentWorkSessionSchema = z.object({
    work_session: workSessionSchema.nullable(),
});

export type CurrentWorkSessionResponse = z.infer<typeof currentWorkSessionSchema>;

/** Lo que el dispositivo aporta como evidencia de tiempo local (D-10). */
export interface TimeEvidence {
    device_captured_at?: string;
    utc_offset_minutes?: number;
}
