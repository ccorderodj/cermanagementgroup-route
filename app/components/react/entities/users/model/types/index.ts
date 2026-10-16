import { z } from 'zod';

/**
 * Tipos de la entidad de sesion y cuenta.
 *
 * Este archivo tenia 313 lineas, de las cuales 287 eran tipos del sistema
 * anterior: `InvoiceReportExtra`, `InvoiceReport`, `SubClient`,
 * `SubClientEmployee`, `SubClientJob`, `SubClientLog` y sus `*Result`/`*Schema`,
 * con campos como `employees_ids_in_invoice`. Nada de eso lo importaba nadie
 * (AUD-LEG-011).
 *
 * Los esquemas Zod son la fuente: el tipo de TypeScript sale de ellos con
 * `z.infer`, asi que no pueden desincronizarse (D14).
 */

export const userProfileSchema = z.object({
    id: z.number(),
    email: z.string(),
    username: z.string(),
    first_name: z.string(),
    last_name: z.string(),
    gender: z.boolean(),
});

export type UserProfile = z.infer<typeof userProfileSchema>;

/** Respuesta de los endpoints publicos de autenticacion. */
export const authAckSchema = z.object({
    success: z.boolean(),
    detail: z.string().optional(),
});

export type AuthAck = z.infer<typeof authAckSchema>;

export interface LoginPayload {
    email: string;
    password: string;
}

export interface PasswordResetRequestPayload {
    email: string;
}

export interface PasswordResetConfirmPayload {
    token: string;
    password: string;
}

/** Estado de la sesion en el store. La contrasena NUNCA se guarda aqui. */
export interface LoginSchema extends GlobalsCommonSchema {
    email: string;
    isAuthenticated: boolean;
}
