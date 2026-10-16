export interface PermissionEntity {
    id: number;
    name: string;
    description?: string | null;
    is_active?: boolean;
}

/**
 * Lo que guarda el slice: la respuesta del servidor mas el estado de la tabla
 * en el cliente (`page_size`, `index_page`). El envoltorio que devuelve la API
 * es `IResultPagination`, que NO trae `page_size` porque el backend no lo envia
 * (AUD-FE-010).
 */
export interface PermissionPaginationResult extends IPaginationState<PermissionEntity> {}

export interface PermissionsPaginationSchema extends GlobalsCommonSchema {
    data: PermissionPaginationResult;
}

/** Un rol que tiene concedida una capacidad. */
export interface PermissionRoleRef {
    name: string;
    category?: string | null;
}

/**
 * Una capacidad del sistema: módulo + acción, y qué roles la tienen.
 *
 * Los permisos no son datos que alguien redacte, se derivan de lo que la
 * aplicación sabe hacer; por eso esta vista es un mapa de lectura y no un CRUD.
 */
export interface FeatureMapItem {
    id: number;
    name: string;
    description?: string | null;
    module: string;
    action: string;
    is_active: boolean;
    roles: PermissionRoleRef[];
}
