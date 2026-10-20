import { z } from 'zod';

/** La captura periódica de ubicación de la compañía (RTE-LOC-02). */
export const captureSettingSchema = z.object({
    enabled: z.boolean(),
    interval_seconds: z.number(),
    /** 0: nunca se guardó (apagada, 300 s). */
    version: z.number(),
    updated_at: z.string().nullable(),
    updated_by_user_id: z.number().nullable(),
    min_interval_seconds: z.number(),
    max_interval_seconds: z.number(),
});

export type CaptureSetting = z.infer<typeof captureSettingSchema>;
