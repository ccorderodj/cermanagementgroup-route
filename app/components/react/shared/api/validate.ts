import { z, ZodType } from 'zod';

/**
 * Validación en runtime de lo que devuelve la API (D14).
 *
 * El problema
 * -----------
 * Las respuestas se tipaban por aserción:
 *
 *     const response = await api.get<RegionsPaginationResult>(url);
 *
 * Eso no comprueba nada. TypeScript se cree lo que le digan, así que un cambio
 * de contrato en el backend no producía ni error de tipos ni error de runtime:
 * el fallo aparecía mucho más tarde, en el componente que leía un campo que ya
 * no venía, y con `undefined` disfrazado del tipo declarado. El caso concreto
 * que encontró la auditoría es `page_size`, declarado obligatorio en
 * `IResultPagination` y que el backend nunca ha enviado (AUD-FE-010).
 *
 * La solución
 * -----------
 * Un helper único. El esquema Zod vive **junto a la entidad**, nunca dentro de
 * un componente, y es la definición de la que sale el tipo de TypeScript: una
 * sola fuente, imposible que se desincronicen.
 *
 *     // entities/Roles/model/types/index.ts
 *     export const roleSchema = z.object({ id: z.number(), name: z.string() });
 *     export type Role = z.infer<typeof roleSchema>;
 *
 *     // en el thunk
 *     return parseApi(z.array(roleSchema), response.data, 'fetchRoles');
 *
 * Si el contrato se rompe, falla aquí —con el nombre del endpoint y el campo
 * exacto— y no tres pantallas más allá.
 */

export class ApiContractError extends Error {
    readonly issues: z.ZodIssue[];

    constructor(context: string, issues: z.ZodIssue[]) {
        const summary = issues
            .slice(0, 3)
            .map((issue) => `${issue.path.join('.') || '(root)'}: ${issue.message}`)
            .join('; ');

        super(`Unexpected API response in ${context} — ${summary}`);
        this.name = 'ApiContractError';
        this.issues = issues;
    }
}

/**
 * Valida `data` contra `schema`.
 *
 * @param context Nombre del thunk o endpoint. Aparece en el mensaje de error,
 *                que es lo que hace la diferencia entre un fallo diagnosticable
 *                y un `undefined` inexplicable.
 */
export function parseApi<T extends ZodType>(
    schema: T,
    data: unknown,
    context: string,
): z.infer<T> {
    const result = schema.safeParse(data);

    if (!result.success) {
        const error = new ApiContractError(context, result.error.issues);
        // Se registra siempre: un contrato roto en producción es información
        // que hay que poder recuperar del navegador de quien lo sufrió.
        // eslint-disable-next-line no-console
        console.error(error.message, result.error.issues);
        throw error;
    }

    return result.data;
}

/**
 * Envoltorio paginado del backend: `{ count, next, previous, results }`.
 *
 * `page_size` NO está aquí, y esa ausencia es el contrato real: el backend no
 * lo envía. El tipo global que lo declaraba obligatorio mentía.
 */
export function paginatedSchema<T extends ZodType>(itemSchema: T) {
    return z.object({
        count: z.number(),
        next: z.string().nullable(),
        previous: z.string().nullable(),
        results: z.array(itemSchema),
    });
}

export type Paginated<T> = {
    count: number;
    next: string | null;
    previous: string | null;
    results: T[];
};
