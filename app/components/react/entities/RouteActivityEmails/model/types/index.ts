import { z } from 'zod';

/** Los dos correos aprobados (BR-01). Cerrados: los define el producto. */
export const ACTIVITY_EMAIL_TYPES = ['midday_motivation', 'end_of_day_recognition'] as const;

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
