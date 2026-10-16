/**
 * Traducción entre la paginación del cliente y la del servidor.
 *
 * TanStack Table trabaja con `pageIndex` **base 0**; el backend con `page`
 * **base 1**. Esa aritmética estaba copiada en los cinco thunks de paginación,
 * lo que garantizaba que el sexto módulo la copiara también (AUD-FE-012).
 *
 *     const params = toServerPageParams({ indexPage, pageSize, filters: { q } });
 *     // { page: 1, page_size: 20, q: 'ana' }
 */

export interface ServerPageParams {
    page: number;
    page_size: number;
    [key: string]: string | number | boolean | undefined;
}

export interface PageRequest {
    /** Índice de página en el cliente, base 0. */
    indexPage: number;
    pageSize: number;
    /** Filtros del módulo. Los valores vacíos se descartan. */
    filters?: Record<string, string | number | boolean | undefined | null>;
}

export function toServerPageParams({
    indexPage,
    pageSize,
    filters = {},
}: PageRequest): ServerPageParams {
    const params: ServerPageParams = {
        page: indexPage + 1,
        page_size: pageSize,
    };

    Object.entries(filters).forEach(([key, value]) => {
        if (value === undefined || value === null || value === '') return;
        params[key] = value as string | number | boolean;
    });

    return params;
}

/** Estado inicial de un slice paginado. */
export function initialPaginationState<T>(pageSize = 10): IPaginationState<T> {
    return {
        results: [] as T[],
        next: null,
        previous: null,
        count: 0,
        page_size: pageSize,
        index_page: 0,
    };
}
