import { z } from 'zod';

/** Los correos aprobados: dos motivacionales y dos reportes estratégicos. */
export const ACTIVITY_EMAIL_TYPES = [
    'midday_motivation',
    'end_of_day_recognition',
    'strategic_midday_report',
    'strategic_end_of_day_report',
] as const;

export const activityEmailTypeSchema = z.enum(ACTIVITY_EMAIL_TYPES);
export type ActivityEmailType = z.infer<typeof activityEmailTypeSchema>;

export const activityEmailTokenSchema = z.object({
    token: z.string(),
    description: z.string(),
    required: z.boolean(),
});

export type ActivityEmailToken = z.infer<typeof activityEmailTokenSchema>;

export const activityEmailTemplateSchema = z.object({
    template_type: activityEmailTypeSchema,
    group: z.enum(['motivational', 'strategic']),
    label: z.string(),
    schedule_label: z.string(),
    send_condition: z.string(),
    subject: z.string(),
    body: z.string(),
    is_default: z.boolean(),
    version: z.number(),
    updated_at: z.string().nullable(),
    updated_by_name: z.string().nullable(),
    subject_tokens: z.array(z.string()),
    tokens: z.array(activityEmailTokenSchema),
});

export type ActivityEmailTemplate = z.infer<typeof activityEmailTemplateSchema>;

/** Vista previa con datos ficticios: `is_sample` es siempre `true`. */
export const activityEmailPreviewSchema = z.object({
    is_sample: z.literal(true),
    sample_label: z.string(),
    subject: z.string(),
    body: z.string(),
});

export type ActivityEmailPreview = z.infer<typeof activityEmailPreviewSchema>;

export const activityEmailRecipientSchema = z.object({
    user_id: z.number(),
    first_name: z.string(),
    last_name: z.string(),
    username: z.string(),
    email: z.string(),
    role_name: z.string().nullable(),
    midday_enabled: z.boolean(),
    end_of_day_enabled: z.boolean(),
    eligible: z.boolean(),
    ineligible_reason: z.enum(['inactive', 'invalid_email']).nullable(),
    version: z.number(),
});

export type ActivityEmailRecipient = z.infer<typeof activityEmailRecipientSchema>;

/** A quién se puede mandar una prueba (RTE-MAIL-TEST-01). */
export const activityEmailTestTargetsSchema = z.object({
    recipients: z.array(z.string()),
    provider_configured: z.boolean(),
    limit: z.number(),
    window_minutes: z.number(),
});

export type ActivityEmailTestTargets = z.infer<typeof activityEmailTestTargetsSchema>;

/** Resultado de una prueba. `delivered_confirmed` es siempre `false`. */
export const activityEmailTestResultSchema = z.object({
    outcome: z.enum(['accepted_by_provider', 'not_sent_development_backend', 'captured_by_test_backend']),
    to: z.string(),
    subject: z.string(),
    backend: z.string().nullable(),
    delivered_confirmed: z.literal(false),
});

export type ActivityEmailTestResult = z.infer<typeof activityEmailTestResultSchema>;

/** Un mando y sus dos interruptores de reporte estratégico (V1.2). */
export const strategicRecipientSchema = z.object({
    user_id: z.number(),
    first_name: z.string(),
    last_name: z.string(),
    email: z.string(),
    role_name: z.string().nullable(),
    coverage: z.number(),
    strategic_midday_enabled: z.boolean(),
    strategic_end_of_day_enabled: z.boolean(),
    eligible: z.boolean(),
    ineligible_reason: z.enum(['inactive', 'invalid_email', 'no_team']).nullable(),
    version: z.number(),
});

export type StrategicRecipient = z.infer<typeof strategicRecipientSchema>;

/** Un envío real (RTE-MAIL-CP4). `accepted_by_provider` no es «entregado». */
export const DELIVERY_STATUSES = [
    'pending',
    'claimed',
    'accepted_by_provider',
    'retryable_failure',
    'permanent_failure',
    'skipped',
    'unknown_outcome',
] as const;

export const deliverySchema = z.object({
    id: z.number(),
    report_type: activityEmailTypeSchema,
    recipient_user_id: z.number(),
    operational_date: z.string(),
    status: z.enum(DELIVERY_STATUSES),
    source: z.enum(['schedule', 'reconcile', 'manual']),
    attempt_count: z.number(),
    cutoff_at: z.string().nullable(),
    due_at: z.string().nullable(),
    last_attempt_at: z.string().nullable(),
    accepted_at: z.string().nullable(),
    reason_code: z.string().nullable(),
    requested_by_user_id: z.number().nullable(),
    provider_backend: z.string().nullable(),
});

export type Delivery = z.infer<typeof deliverySchema>;

/** Un reenvío de un correo que ya salió. Numerado desde 1. */
export const resendSchema = z.object({
    id: z.number(),
    sequence: z.number(),
    status: z.enum(DELIVERY_STATUSES),
    reason_code: z.string().nullable(),
    requested_by_user_id: z.number().nullable(),
    provider_backend: z.string().nullable(),
    accepted_at: z.string().nullable(),
    created_at: z.string(),
});

export type Resend = z.infer<typeof resendSchema>;

/** La vista previa con datos reales: generarla no escribe ni envía nada. */
export const realReportPreviewSchema = z.object({
    report_type: activityEmailTypeSchema,
    recipient_user_id: z.number(),
    recipient_name: z.string(),
    destination_masked: z.string().nullable(),
    operational_date: z.string(),
    time_zone: z.string().nullable(),
    cutoff_at: z.string().nullable(),
    due_at: z.string().nullable(),
    generated_at: z.string(),
    provisional: z.boolean(),
    eligible: z.boolean(),
    reason_code: z.string().nullable(),
    reason_message: z.string().nullable(),
    coverage: z.number().nullable(),
    activity_count: z.number(),
    subject: z.string().nullable(),
    body: z.string().nullable(),
    can_send: z.boolean(),
    blocked_reason: z.string().nullable(),
    blocked_message: z.string().nullable(),
    delivery: deliverySchema.nullable(),
    can_resend: z.boolean(),
    resend_blocked_reason: z.string().nullable(),
    resend_blocked_message: z.string().nullable(),
    resends: z.array(resendSchema),
});

export type RealReportPreview = z.infer<typeof realReportPreviewSchema>;

export const reportSendResultSchema = deliverySchema.extend({
    destination_masked: z.string().nullable(),
});

export type ReportSendResult = z.infer<typeof reportSendResultSchema>;

export const resendResultSchema = resendSchema.extend({
    destination_masked: z.string().nullable(),
});

export type ResendResult = z.infer<typeof resendResultSchema>;

/** Una fila de Delivery History: la entrega y sus reenvíos, sin contenido. */
export const deliveryHistorySchema = deliverySchema.extend({
    recipient_name: z.string(),
    time_zone: z.string().nullable(),
    next_attempt_at: z.string().nullable(),
    delay_seconds: z.number().nullable(),
    reason_message: z.string().nullable(),
    resends: z.array(resendSchema.extend({ reason_message: z.string().nullable() })),
});

export type DeliveryHistory = z.infer<typeof deliveryHistorySchema>;

export const DELIVERY_TRIGGERS = ['scheduler', 'reconcile', 'manual', 'resend'] as const;
export type DeliveryTrigger = (typeof DELIVERY_TRIGGERS)[number];

/** La última pasada vista de un reloj del envío automático. */
export const dispatchRunSchema = z.object({
    source: z.enum(['schedule', 'reconcile']),
    started_at: z.string(),
    finished_at: z.string(),
    outcome: z.enum(['completed', 'failed']),
    enabled: z.boolean(),
    dry_run: z.boolean(),
    counts: z.record(z.string(), z.number()),
});

export type DispatchRun = z.infer<typeof dispatchRunSchema>;

/** El estado del envío, leído del servidor. */
export const operationalStatusSchema = z.object({
    provider_status: z.string(),
    provider_verified_at: z.string().nullable(),
    automation_enabled: z.boolean(),
    dry_run: z.boolean(),
    real_send_types: z.array(activityEmailTypeSchema),
    recovery_window_hours: z.number(),
    runs: z.array(dispatchRunSchema),
});

export type OperationalStatus = z.infer<typeof operationalStatusSchema>;
