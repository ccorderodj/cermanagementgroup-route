export type RolePermissionRequestUserEntity = Pick<
    UserLogged,
    'user_id' | 'username' | 'first_name' | 'last_name' | 'email'
>;

export type ChangeRequestStatus = 'pending' | 'approved' | 'rejected';

export interface RolePermissionChangeRequestEntity {
    id: number;
    role_id: number;
    role_name?: string | null;
    /** 'management' puede aprobar; 'operative' solo solicitar. */
    role_category?: string | null;
    requested_by_user_id: number;
    reviewed_by_user_id?: number | null;
    requested_by_user: RolePermissionRequestUserEntity;
    reviewed_by_user?: RolePermissionRequestUserEntity | null;
    status: ChangeRequestStatus;
    is_active: boolean;
    review_note?: string | null;
    created_at: string;
    updated_at: string;

    /** Conceder y revocar son dos actividades distintas. */
    to_grant: string[];
    to_revoke: string[];

    /** Si quien consulta puede revisarla, y si no, por qué. */
    can_review: boolean;
    cannot_review_reason?: string | null;
}

/**
 * Lo que guarda el slice: la respuesta del servidor mas el estado de la tabla
 * en el cliente (`page_size`, `index_page`). El envoltorio que devuelve la API
 * es `IResultPagination`, que NO trae `page_size` porque el backend no lo envia
 * (AUD-FE-010).
 */
export interface RolePermissionChangeRequestPaginationResult extends IPaginationState<RolePermissionChangeRequestEntity> {}

export interface RolePermissionChangeRequestsPaginationSchema extends GlobalsCommonSchema {
    data: RolePermissionChangeRequestPaginationResult;
}
