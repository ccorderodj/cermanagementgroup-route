import { z } from 'zod';

/**
 * Integraciones, políticas, preparación y Diagnostics de la plataforma.
 *
 * Tres cosas que la pantalla **no** calcula: el estado de una integración, si
 * un gate está cerrado y si la plataforma está lista para producción. Llegan
 * resueltas de `readiness.py`, que es la única fuente. Recalcularlas aquí haría
 * que Settings dijera «verificada» mientras la matriz dice «abierta» (S1).
 *
 * Ningún esquema tiene sitio para el valor de un secreto: de una credencial
 * llega si está puesta, cuándo y hasta cuándo vale.
 */

const nullableString = z.string().nullable().optional();

export const providerFieldSchema = z.object({
    name: z.string(),
    label: z.string(),
    /** public_identifier · secret · endpoint · mailbox · choice · policy · preset */
    kind: z.string(),
    source: z.string(),
    format: z.string(),
    required: z.boolean(),
    default: z.union([z.string(), z.number(), z.boolean()]).nullable().optional(),
    choices: z.array(z.string()),
    /** La misma expresión con la que valida el servidor. */
    pattern: nullableString,
    expires: z.boolean(),
});

export type ProviderField = z.infer<typeof providerFieldSchema>;

export const providerSchema = z.object({
    key: z.string(),
    title: z.string(),
    summary: z.string(),
    who: z.string(),
    recommended: z.boolean(),
    available: z.boolean(),
    steps: z.array(z.object({ text: z.string(), link: nullableString })),
    fields: z.array(providerFieldSchema),
    warnings: z.array(z.string()),
    docs: z.array(z.object({ label: z.string(), url: z.string() })),
});

export type Provider = z.infer<typeof providerSchema>;

export const secretStateSchema = z.object({
    name: z.string(),
    label: z.string(),
    present: z.boolean(),
    set_at: nullableString,
    expires_at: nullableString,
});

export type SecretState = z.infer<typeof secretStateSchema>;

export const integrationSchema = z.object({
    key: z.string(),
    title: z.string(),
    summary: z.string(),
    required: z.boolean(),
    open_decision: nullableString,
    providers: z.array(providerSchema),
    provider: nullableString,
    enabled: z.boolean(),
    /** not_configured · unavailable · disabled · incomplete · master_key_missing · failing · configured · verified */
    status: z.string(),
    missing: z.array(z.string()),
    config: z.record(z.union([z.string(), z.number(), z.boolean()])),
    secrets: z.array(secretStateSchema),
    verified_at: nullableString,
    version: z.number(),
});

export type Integration = z.infer<typeof integrationSchema>;

export const policySchema = z.object({
    key: z.string(),
    title: z.string(),
    summary: z.string(),
    value: z.record(z.unknown()),
    defaults: z.record(z.unknown()),
    customized: z.boolean(),
    version: z.number(),
});

export type Policy = z.infer<typeof policySchema>;

export const gateSchema = z.object({
    key: z.string(),
    title: z.string(),
    /** closed · open · waiting_cer */
    status: z.string(),
    blocks_production: z.boolean(),
    detail: z.string(),
    /** settings · diagnostics · deployment · cer */
    action: z.string(),
    open_decision: nullableString,
});

export type Gate = z.infer<typeof gateSchema>;

export const readinessSchema = z.object({
    production_ready: z.boolean(),
    mode: z.string(),
    counts: z.record(z.number()),
    gates: z.array(gateSchema),
});

export type Readiness = z.infer<typeof readinessSchema>;

export const postureItemSchema = z.object({
    key: z.string(),
    title: z.string(),
    value: z.string(),
    ok: z.boolean(),
    detail: z.string(),
});

export type PostureItem = z.infer<typeof postureItemSchema>;

export const checkSchema = z.object({
    key: z.string(),
    title: z.string(),
    /** infrastructure · integration · integrity · platform */
    kind: z.string(),
    summary: z.string(),
    status: z.string(),
    detail: nullableString,
    last_checked_at: nullableString,
    last_success_at: nullableString,
});

export type Check = z.infer<typeof checkSchema>;

export const checkRunSchema = z.object({
    id: z.number().nullable().optional(),
    capability_key: z.string(),
    status: z.string(),
    detail: nullableString,
    checked_at: z.string(),
    duration_ms: z.number().nullable().optional(),
    /** manual · scheduled · verify */
    trigger: z.string(),
    actor_user_id: z.number().nullable().optional(),
});

export type CheckRun = z.infer<typeof checkRunSchema>;

export const verifyResultSchema = z.object({
    integration: integrationSchema,
    check: checkRunSchema,
});

export const platformAuditSchema = z.object({
    id: z.number(),
    occurred_at: z.string(),
    actor_user_id: z.number().nullable().optional(),
    actor_role: nullableString,
    action: z.string(),
    target: z.string(),
    changes: z.record(z.unknown()).nullable().optional(),
    request_id: nullableString,
});

export type PlatformAudit = z.infer<typeof platformAuditSchema>;

export interface PlatformSettingsSchema {
    integrations: Integration[];
    policies: Policy[];
    posture: PostureItem[];
    readiness?: Readiness;
    checks: Check[];
    history: Record<string, CheckRun[]>;
    audit: PlatformAudit[];
    isLoading: boolean;
    error?: string;
}
