import { z } from 'zod';

/**
 * Today / Live: el estado operativo del día.
 *
 * Es un **modelo de lectura**. No posee ningún dato: la jornada, el viaje, la
 * actividad y el millaje oficial viven en sus dominios, y esto los mira. Por eso
 * no hay acciones ni mutaciones en esta entidad, y no debe haberlas.
 */

/**
 * Los cuatro estados que enseña el mockup aprobado V0.7, más el que la lista
 * necesita para no mentir.
 *
 * `not_started` no es un estado nuevo del dominio: V0.7 dibuja a **todos** los
 * supervisores autorizados, y quien hoy no ha empezado no puede desaparecer ni
 * aparecer como "Working". Lo decide el servidor, no esta pantalla.
 */
export const liveStatusSchema = z.enum([
    'route',
    'activity',
    'ended',
    'working',
    'not_started',
]);
export type LiveStatus = z.infer<typeof liveStatusSchema>;

/**
 * Las etiquetas visibles, tal como las fija `statusMeta()` del mockup aprobado.
 *
 * No se traducen ni se "mejoran": la terminología es del producto y §14 prohíbe
 * cambiarla porque otra palabra parezca más clara.
 */
export const LIVE_STATUS_LABEL: Record<LiveStatus, string> = {
    route: 'On Route',
    activity: 'In Activity',
    ended: 'Work Ended',
    working: 'Working',
    not_started: 'Not started',
};

/** La clase del punto de color, también del mockup. */
export const LIVE_STATUS_TONE: Record<LiveStatus, string> = {
    route: 'bg-blue-500',
    activity: 'bg-emerald-500',
    ended: 'bg-muted-foreground',
    working: 'bg-emerald-500',
    not_started: 'bg-muted-foreground/50',
};

/**
 * Decimales por cable: el servidor los serializa como cadena para no perder
 * precisión al pasar por el doble de coma flotante de JavaScript.
 */
const decimalSchema = z.union([z.string(), z.number()]);

export const liveSupervisorSchema = z.object({
    supervisor_profile_id: z.number(),
    user_id: z.number(),
    name: z.string(),
    initials: z.string(),

    status: liveStatusSchema,
    since: z.string().nullable().optional(),

    vehicle_label: z.string().nullable().optional(),
    activity_label: z.string().nullable().optional(),
    activity_reference: z.string().nullable().optional(),

    official_miles: decimalSchema,
    // Pendiente **no** es cero. Un total que presenta un viaje sin calcular
    // como cero millas parece final y no lo es.
    mileage_pending: z.boolean(),

    activities_today: z.number(),
    operational_mpg: decimalSchema.nullable().optional(),
    fuel_grade: z.string().nullable().optional(),
});
export type LiveSupervisor = z.infer<typeof liveSupervisorSchema>;

export const liveSummarySchema = z.object({
    supervisors_working: z.number(),
    supervisors_total: z.number(),
    total_miles: decimalSchema,
    on_route: z.number(),
    in_activity: z.number(),
});
export type LiveSummary = z.infer<typeof liveSummarySchema>;

export const liveTodaySchema = z.object({
    session_date: z.string(),
    generated_at: z.string(),
    summary: liveSummarySchema,
    supervisors: z.array(liveSupervisorSchema),
});
export type LiveToday = z.infer<typeof liveTodaySchema>;

/** Las millas, tal como las enseña V0.7: un decimal y el sufijo. */
export const formatMiles = (valor: string | number): string => (
    `${Number(valor).toFixed(1)} mi`
);

/**
 * La hora desde la que dura el estado actual, en el formato del mockup.
 *
 * `null` cuando no hay estado — y entonces la pantalla no escribe una hora
 * inventada, escribe el guion neutro.
 */
export const formatSince = (iso: string | null | undefined): string => {
    if (!iso) return '—';
    const fecha = new Date(iso);
    if (Number.isNaN(fecha.getTime())) return '—';
    return fecha.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
};
