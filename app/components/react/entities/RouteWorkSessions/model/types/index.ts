import { z } from 'zod';
import { tripSchema } from '@/entities/RouteTrips';
import { activityExecutionSchema } from '@/entities/RouteActivities';

/**
 * La Jornada, tal y como la sirve `GET /worksessions/current`.
 *
 * `started_at`/`ended_at` son **ocurrencia**: cuándo pulsó el botón el
 * supervisor, que puede ser bastante antes de que el servidor lo recibiera si
 * la acción esperó en la cola offline. Es lo que la pantalla muestra.
 * `*_received_at` es la hora de recepción del servidor y `*_at_source` dice de
 * cuál de los dos relojes salió la ocurrencia.
 */
export const workSessionSchema = z.object({
    id: z.number(),
    status: z.enum(['active', 'ended']),
    session_date: z.string(),
    started_at: z.string(),
    started_received_at: z.string(),
    started_at_source: z.enum(['device', 'server_receipt']),
    /** Zona efectiva de la jornada (T-1/T-2). Nula en las anteriores. */
    start_time_zone: z.string().nullable().optional(),
    ended_at: z.string().nullable().optional(),
    ended_received_at: z.string().nullable().optional(),
    ended_at_source: z.enum(['device', 'server_receipt']).nullable().optional(),
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
 * Crece, no se duplica: RTE04 añadió `current_trip` a este mismo tipo y RTE05
 * añade `current_activity` igual. Nunca un segundo endpoint de estado — dos
 * fuentes de verdad para la misma pregunta acaban discrepando.
 *
 * `post_arrival_pending` es la pregunta que decide la navegación: si queda
 * trabajo de llegada sin resolver. La responde el servidor para que la pantalla
 * no tenga que deducirla cruzando propósito, estado del viaje y estado del
 * bloque — y para que las dos no puedan discrepar.
 */
export const currentWorkSessionSchema = z.object({
    work_session: workSessionSchema.nullable(),
    // El viaje **vivo**, si lo hay. Un viaje operativo en `arrived` sigue
    // siéndolo —espera a RTE05—; uno cerrado o interrumpido ya no.
    current_trip: tripSchema.nullable().optional(),
    current_activity: activityExecutionSchema.nullable().optional(),
    post_arrival_pending: z.boolean().default(false),
});

export type CurrentWorkSessionResponse = z.infer<typeof currentWorkSessionSchema>;
