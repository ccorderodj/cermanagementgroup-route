import { z } from 'zod';

/**
 * Un usuario tal y como lo ve quien administra ESTA compania.
 *
 * `is_active` es el estado de la **pertenencia** a esta compania: es lo que
 * administra el tenant. `is_platform_active` es la identidad global y viene
 * como informacion de solo lectura. `is_superuser` tambien es informativo: no
 * se puede conceder ni retirar desde ninguna API de tenant (D6, AUD-SEC-012).
 */
export const userManagementSchema = z.object({
    id: z.number(),
    username: z.string(),
    email: z.string().nullable().optional(),
    first_name: z.string().nullable().optional(),
    last_name: z.string().nullable().optional(),
    gender: z.boolean(),
    is_active: z.boolean(),
    is_platform_active: z.boolean(),
    is_superuser: z.boolean(),
    last_login: z.string().nullable().optional(),
    date_joined: z.string().nullable().optional(),
    created_at: z.string(),
    updated_at: z.string(),
    company_id: z.number().nullable().optional(),
    role_id: z.number().nullable().optional(),
    role_name: z.string().nullable().optional(),
});

export type UserManagementEntity = z.infer<typeof userManagementSchema>;

/**
 * Lo que guarda el slice: la respuesta del servidor mas el estado de la tabla
 * en el cliente (`page_size`, `index_page`). El envoltorio que devuelve la API
 * es `IResultPagination`, que NO trae `page_size` porque el backend no lo envia
 * (AUD-FE-010).
 */
export interface UserManagementPaginationResult extends IPaginationState<UserManagementEntity> {}

export interface UserManagementPaginationSchema extends GlobalsCommonSchema {
    data: UserManagementPaginationResult;
}
