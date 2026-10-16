import { z } from 'zod';
import { formatPeriod } from '@/entities/RouteActivityExplorer';

/**
 * Los contratos de Reports (RTE09), validados al entrar.
 *
 * El coste estimado viaja como **número** y, al lado, su **estado**. La
 * pantalla nunca deduce si un `$0.00` es un resultado o una espera mirando el
 * texto: lo dice `fuel_cost_status` (RTE09 §12).
 */

/** Los tres rangos de las pestañas del V0.7, en su orden. */
export const reportRangeSchema = z.enum(['week', 'month', 'year']);
export type ReportRange = z.infer<typeof reportRangeSchema>;
export const REPORT_RANGES: ReportRange[] = ['week', 'month', 'year'];

const decimalSchema = z.union([z.string(), z.number()]);

export const fuelCostStatusSchema = z.enum([
    'calculated', 'partial', 'waiting_reference', 'missing_input', 'none',
]);
export type FuelCostStatus = z.infer<typeof fuelCostStatusSchema>;

const metricas = {
    official_miles: decimalSchema,
    mileage_pending: z.boolean(),
    mileage_unresolved: z.number().int().nonnegative().default(0),
    activity_seconds: z.number(),
    has_open_activity: z.boolean(),
    activities: z.number(),
    estimated_gallons: decimalSchema.nullable().optional(),
    estimated_fuel_cost: decimalSchema,
    fuel_cost_status: fuelCostStatusSchema,
};

export const reportMetricsSchema = z.object(metricas);
export type ReportMetrics = z.infer<typeof reportMetricsSchema>;

export const reportGroupSchema = z.object({
    ...metricas,
    start: z.string(),
    end: z.string(),
});
export type ReportGroup = z.infer<typeof reportGroupSchema>;

export const reportBreakdownRowSchema = z.object({ ...metricas, purpose: z.string() });
export type ReportBreakdownRow = z.infer<typeof reportBreakdownRowSchema>;

/** Un periodo o subgrupo por sus fechas: el identificador que viaja al API. */
export const reportPeriodSchema = z.object({ start: z.string(), end: z.string() });
export type ReportPeriod = z.infer<typeof reportPeriodSchema>;

export const reportSupervisorSchema = z.object({ user_id: z.number(), name: z.string() });
export type ReportSupervisor = z.infer<typeof reportSupervisorSchema>;

export const reportViewSchema = z.object({
    range: reportRangeSchema,
    start: z.string(),
    end: z.string(),
    grouped_by: z.enum(['day', 'week', 'month']),
    supervisors: z.array(reportSupervisorSchema),
    /** `null`: *All Supervisors*. */
    supervisor_user_id: z.number().nullable().optional(),
    /** Opciones del selector de periodo, de la más reciente a la más antigua. */
    periods: z.array(reportPeriodSchema),
    summary: reportMetricsSchema,
    groups: z.array(reportGroupSchema),
    /** El subgrupo al que se acota el desglose; `null`: el periodo entero. */
    selected_group: reportPeriodSchema.nullable().optional(),
    breakdown: z.array(reportBreakdownRowSchema),
    breakdown_excluded: z.array(reportBreakdownRowSchema),
    activity_types: z.array(z.object({ label: z.string(), count: z.number() })),
    fuel: z.object({
        sessions: z.number(),
        calculated: z.number(),
        final: z.number(),
        waiting_reference: z.number(),
        missing_input: z.number(),
        missing: z.record(z.string(), z.number()),
    }),
});
export type ReportView = z.infer<typeof reportViewSchema>;

/**
 * `$1,234.56`. El valor es el que da el servidor: aquí sólo se formatea. Un
 * `0` en espera de referencia se ve `$0.00`, que es la decisión de producto
 * (autorización §8); lo que significa lo dice `fuel_cost_status`.
 */
export function formatMoney(value: string | number): string {
    const n = typeof value === 'number' ? value : Number.parseFloat(value || '0');
    return (Number.isFinite(n) ? n : 0).toLocaleString('en-US', {
        style: 'currency',
        currency: 'USD',
    });
}

/**
 * La etiqueta de una opción del selector de periodo, sin ambigüedad sobre su
 * tipo: `Oct 12–18, 2026`, `October 2026`, `2026`.
 */
export function formatReportPeriod(range: ReportRange, start: string, end: string): string {
    const base = formatPeriod(range, start, end);
    return range === 'week' ? `${base}, ${start.slice(0, 4)}` : base;
}
