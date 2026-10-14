import { z } from 'zod';

/**
 * La estructura organizacional de CER Route: cargo y superior.
 *
 * El cargo **organiza**; no concede nada. Lo que alguien puede hacer sale de su
 * rol y sobre quién lo decide el servidor con esta estructura. Estas opciones
 * son experiencia: el servidor vuelve a validar todo al guardar.
 */

export const orgAssignmentSchema = z.object({
    user_id: z.number(),
    name: z.string(),
    position: z.string(),
    position_label: z.string(),
    superior_user_id: z.number().nullable().optional(),
    superior_name: z.string().nullable().optional(),
    version: z.number(),
});
export type OrgAssignment = z.infer<typeof orgAssignmentSchema>;

export const orgOptionsSchema = z.object({
    positions: z.array(z.object({ code: z.string(), label: z.string(), level: z.number() })),
    superiors: z.array(z.object({
        user_id: z.number(),
        name: z.string(),
        position: z.string(),
        level: z.number(),
    })),
    superior_required: z.boolean(),
    /** V1.3: el cargo de cada rol y de qué cargos puede depender cada cargo. */
    role_positions: z.record(z.string(), z.string()),
    allowed_parents: z.record(z.string(), z.array(z.string())),
    current: orgAssignmentSchema.nullable().optional(),
});
export type OrgOptions = z.infer<typeof orgOptionsSchema>;
