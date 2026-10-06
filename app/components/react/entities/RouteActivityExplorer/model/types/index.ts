import { z } from 'zod';

/**
 * Los contratos del Activity Explorer, validados al entrar.
 *
 * Por qué el formato de las etiquetas vive aquí
 * ----------------------------------------------
 * El servidor devuelve **fechas** y el nivel; las cadenas visibles —`Sep 14–20`,
 * `Mon Sep 14`, `January`— se componen en esta capa. La **convención** es del
 * dominio y se prueba allí; el idioma y el formato son presentación, igual que
 * las etiquetas de estado de Today / Live.
 */

/** Los cuatro rangos de las pestañas de la línea base, en su orden. */
export const explorerRangeSchema = z.enum(['day', 'week', 'month', 'year']);
export type ExplorerRange = z.infer<typeof explorerRangeSchema>;

export const EXPLORER_RANGES: ExplorerRange[] = ['day', 'week', 'month', 'year'];

/** El nivel por el que agrupa cada rango, según `groupRows()` del mockup. */
export const explorerGroupedBySchema = z.enum(['month', 'week', 'day']);
export type ExplorerGroupedBy = z.infer<typeof explorerGroupedBySchema>;

/**
 * Decimales por cable: el servidor los serializa como cadena para no perder
 * precisión al pasar por el doble de coma flotante de JavaScript.
 */
const decimalSchema = z.union([z.string(), z.number()]);

export const explorerGroupSchema = z.object({
    start: z.string(),
    end: z.string(),
    drill_date: z.string(),
    official_miles: decimalSchema,
    mileage_pending: z.boolean(),
    activities: z.number(),
    activity_seconds: z.number(),
    has_open_activity: z.boolean(),
});
export type ExplorerGroup = z.infer<typeof explorerGroupSchema>;

export const explorerActivitySchema = z.object({
    activity_execution_id: z.number(),
    trip_id: z.number(),
    purpose: z.string(),
    context_reference: z.string().nullable().optional(),
    activity_labels: z.array(z.string()),
    purpose_detail: z.string().nullable().optional(),
    trip_started_at: z.string().nullable().optional(),
    arrived_at: z.string().nullable().optional(),
    started_at: z.string(),
    ended_at: z.string().nullable().optional(),
    official_miles: decimalSchema,
    mileage_pending: z.boolean(),
    terminal_action: z.string().nullable().optional(),
    outcome_label: z.string().nullable().optional(),
    notes: z.string().nullable().optional(),
    supervisor_user_id: z.number(),
    supervisor_name: z.string(),
});
export type ExplorerActivity = z.infer<typeof explorerActivitySchema>;

export const explorerSummarySchema = z.object({
    official_miles: decimalSchema,
    mileage_pending: z.boolean(),
    activity_seconds: z.number(),
    has_open_activity: z.boolean(),
    activities: z.number(),
});
export type ExplorerSummary = z.infer<typeof explorerSummarySchema>;

export const explorerSupervisorSchema = z.object({
    user_id: z.number(),
    name: z.string(),
});
export type ExplorerSupervisor = z.infer<typeof explorerSupervisorSchema>;

export const explorerViewSchema = z.object({
    range: explorerRangeSchema,
    start: z.string(),
    end: z.string(),
    grouped_by: explorerGroupedBySchema.nullable().optional(),
    supervisors: z.array(explorerSupervisorSchema),
    supervisor_user_id: z.number().nullable().optional(),
    groups: z.array(explorerGroupSchema),
    summary: explorerSummarySchema.nullable().optional(),
    activities: z.array(explorerActivitySchema),
});
export type ExplorerView = z.infer<typeof explorerViewSchema>;

/**
 * Los propósitos de viaje con su etiqueta aprobada.
 *
 * Son las del mockup —`Client Visit`, `Employee Visit`, `Office`,
 * `Check Delivery`— y no se traducen ni se reescriben: §17 prohíbe cambiar la
 * terminología porque otra palabra parezca más clara.
 */
export const TRIP_PURPOSE_LABEL: Record<string, string> = {
    client_visit: 'Client Visit',
    recruiting: 'Recruiting',
    employee_visit: 'Employee Visit',
    check_delivery: 'Check Delivery',
    office: 'Office',
    other: 'Other',
    home: 'Home',
};

const MESES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
];
const DIAS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MESES_CORTOS = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

/** Una fecha `YYYY-MM-DD` como fecha local, sin que la zona la desplace. */
export function parseDay(iso: string): Date {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, (m ?? 1) - 1, d ?? 1);
}

/**
 * El título del periodo, con los formatos exactos de la línea base:
 * `2026` para el año, `September 2026` para el mes, `Sep 14–20` para la semana
 * y `Mon Sep 14` para el día.
 */
export function formatPeriod(range: ExplorerRange, start: string, end: string): string {
    const a = parseDay(start);
    if (range === 'year') return `${a.getFullYear()}`;
    if (range === 'month') return `${MESES[a.getMonth()]} ${a.getFullYear()}`;
    if (range === 'day') {
        return `${DIAS[a.getDay()]} ${MESES_CORTOS[a.getMonth()]} ${a.getDate()}`;
    }
    const b = parseDay(end);
    const cola = a.getMonth() === b.getMonth()
        ? `${b.getDate()}`
        : `${MESES_CORTOS[b.getMonth()]} ${b.getDate()}`;
    return `${MESES_CORTOS[a.getMonth()]} ${a.getDate()}–${cola}`;
}

/** La etiqueta de una fila de grupo, según el nivel por el que se agrupa. */
export function formatGroupLabel(
    groupedBy: ExplorerGroupedBy,
    group: ExplorerGroup,
): string {
    if (groupedBy === 'month') {
        return MESES[parseDay(group.start).getMonth()];
    }
    if (groupedBy === 'day') {
        return formatPeriod('day', group.start, group.end);
    }
    return formatPeriod('week', group.start, group.end);
}

export function formatMiles(value: string | number): string {
    const n = typeof value === 'number' ? value : Number.parseFloat(value || '0');
    return Number.isFinite(n) ? n.toFixed(1) : '0.0';
}

/**
 * Una duración en `8h 42m`, como la línea base.
 *
 * Un periodo con un bloque todavía abierto dice `In progress` en vez de dar un
 * total: el bloque no ha terminado, así que el total no existe todavía. Es la
 * misma distinción que hace el mockup en su fila del viernes.
 */
export function formatDuration(seconds: number, hasOpen = false): string {
    if (hasOpen && seconds === 0) return 'In progress';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const base = h > 0 ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m`;
    return hasOpen ? `${base} +` : base;
}

/** Una hora del día en `7:51 AM`. `In progress` cuando el hecho no existe aún. */
export function formatClock(iso?: string | null): string {
    if (!iso) return 'In progress';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '—';
    return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

/** El tramo entre dos instantes, en `32m`. Neutro si falta alguno. */
export function spanBetween(from?: string | null, to?: string | null): string {
    if (!from || !to) return '—';
    const ms = new Date(to).getTime() - new Date(from).getTime();
    if (!Number.isFinite(ms) || ms < 0) return '—';
    return formatDuration(Math.round(ms / 1000));
}
