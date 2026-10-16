import {
    AnyAction, EnhancedStore, Reducer, ReducersMapObject,
} from '@reduxjs/toolkit';
import { Dispatch } from 'redux';
import { AxiosInstance } from 'axios';

import { LoginSchema } from '@/entities/users';
import { RegionsSchema, RegionsPaginationSchema } from '@/entities/Regions';
import { CompaniesPaginationSchema, CompaniesSchema } from '@/entities/Companies';
import { PermissionsPaginationSchema } from '@/entities/Permissions';
import { RolePermissionChangeRequestsPaginationSchema } from '@/entities/RolePermissionChangeRequests';
import { RolesPaginationSchema } from '@/entities/Roles';
import { UserManagementPaginationSchema } from '@/entities/UserManagement';
import { PlatformSettingsSchema } from '@/entities/PlatformSettings';

/**
 * Estado global de la aplicación.
 *
 * Solo el núcleo de identidad, RBAC, organización y plataforma. Cada módulo de
 * dominio de una aplicación construida sobre esta base registra aquí su clave
 * (ver `docs/DOMAIN_EXTENSION_GUIDE.md`).
 *
 * Se retiraron `state`, `stateCities` y `countries`: sus thunks llamaban a
 * `/states`, `/states/{id}/cities` y `/countries`, endpoints que no existen en
 * el backend, y ningún componente los consumía (AUD-FE-002). También `api`, el
 * reducer de RTK Query, que estaba montado con cero endpoints definidos y
 * convivía con Axios como segundo cliente HTTP (D13, AUD-FE-011).
 */
export interface StateSchema {
    // Sesión
    login: LoginSchema,

    // Catálogos geográficos
    regions: RegionsSchema,
    regionsPagination: RegionsPaginationSchema,

    // Organización
    companies: CompaniesSchema,
    companiesPagination: CompaniesPaginationSchema,

    // Seguridad / RBAC
    permissionsPagination: PermissionsPaginationSchema,
    rolePermissionChangeRequestsPagination: RolePermissionChangeRequestsPaginationSchema,
    rolesPagination: RolesPaginationSchema,
    userManagementPagination: UserManagementPaginationSchema,

    // Plataforma
    platformSettings: PlatformSettingsSchema,
}

export type StateSchemaKey = keyof StateSchema;
export type MountedReducers = OptionalRecord<StateSchemaKey, boolean>;

export interface ReducerManager {
    getReducerMap: () => ReducersMapObject<StateSchema>;
    reduce: (state: StateSchema, action: AnyAction) => StateSchema;
    add: (key: StateSchemaKey, reducer: Reducer) => void;
    remove: (key: StateSchemaKey) => void;
    getMountedReducers: () => MountedReducers;
}

export interface ReduxStoreWithManager extends EnhancedStore<StateSchema> {
    reducerManager: ReducerManager;
}

export interface ThunkExtraArg {
    api: AxiosInstance;
}

export interface ThunkConfig<T> {
    rejectValue: T;
    extra: ThunkExtraArg;
    dispatch?: Dispatch;
    state: StateSchema
}
