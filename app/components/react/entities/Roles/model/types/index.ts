export interface RoleEntity {
    id: number;
    name: string;
    description?: string | null;
    is_active?: boolean;
    /** Cuántos permisos otorga. Lo resuelve el backend desde role_permission. */
    permission_count?: number;
    /** 'management' puede aprobar cambios de permisos; 'operative' solo pedirlos. */
    category?: string;
}

/**
 * Un permiso del catálogo, con la marca de si este rol lo tiene concedido.
 * El backend devuelve el catálogo completo para poder pintar la pantalla de
 * una sola vez.
 */
export interface RolePermissionCatalogItem {
    id: number;
    name: string;
    description?: string | null;
    module: string;
    action: string;
    granted: boolean;
}

/**
 * Lo que guarda el slice: la respuesta del servidor mas el estado de la tabla
 * en el cliente (`page_size`, `index_page`). El envoltorio que devuelve la API
 * es `IResultPagination`, que NO trae `page_size` porque el backend no lo envia
 * (AUD-FE-010).
 */
export interface RolePaginationResult extends IPaginationState<RoleEntity> {}

export interface RolesPaginationSchema extends GlobalsCommonSchema {
    data: RolePaginationResult;
}

/** Solicitud de cambio de permisos esperando revisión de otro administrador. */
export interface RolePermissionPendingRequest {
    id: number;
    role_id: number;
    requested_by_user_id?: number | null;
    created_at: string;
    /** Conceder y revocar, por separado. */
    to_grant: string[];
    to_revoke: string[];
}

/** Respuesta de `/roles/{id}/permissions`: catálogo + cambio pendiente. */
export interface RolePermissionsView {
    permissions: RolePermissionCatalogItem[];
    pending_request?: RolePermissionPendingRequest | null;
}
