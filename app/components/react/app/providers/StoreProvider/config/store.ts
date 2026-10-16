import {
    configureStore, Reducer, ReducersMapObject,
} from '@reduxjs/toolkit';
import { $api } from '@/shared/api';
import { StateSchema, ThunkExtraArg } from './StateSchema';
import { createReducerManager } from './reducerManager';

import { loginSliceReducer } from '@/entities/users';
import {
    regionsSliceReducer,
    regionsPaginationSliceReducer,
} from '@/entities/Regions';
import {
    companiesSliceReducer,
    companiesPaginationSliceReducer,
} from '@/entities/Companies';
import { permissionsPaginationSliceReducer } from '@/entities/Permissions';
import {
    rolePermissionChangeRequestsPaginationSliceReducer,
} from '@/entities/RolePermissionChangeRequests';
import { rolesPaginationSliceReducer } from '@/entities/Roles';
import { userManagementPaginationSliceReducer } from '@/entities/UserManagement';
import { platformSettingsSliceReducer } from '@/entities/PlatformSettings';

export function createReduxStore(
    initialState?: StateSchema,
    asyncReducers?: ReducersMapObject<StateSchema>,
) {
    const rootReducer: ReducersMapObject<StateSchema> = {
        ...asyncReducers,

        // Sesión
        login: loginSliceReducer,

        // Catálogos geográficos
        regions: regionsSliceReducer,
        regionsPagination: regionsPaginationSliceReducer,

        // Organización
        companies: companiesSliceReducer,
        companiesPagination: companiesPaginationSliceReducer,

        // Seguridad / RBAC
        permissionsPagination: permissionsPaginationSliceReducer,
        rolePermissionChangeRequestsPagination: rolePermissionChangeRequestsPaginationSliceReducer,
        rolesPagination: rolesPaginationSliceReducer,
        userManagementPagination: userManagementPaginationSliceReducer,

        // Plataforma
        platformSettings: platformSettingsSliceReducer,
    };

    const reducerManager = createReducerManager(rootReducer);

    const extraArg: ThunkExtraArg = { api: $api };

    const store = configureStore({
        reducer: reducerManager.reduce as Reducer<StateSchema>,
        // Las DevTools exponen todo el estado, incluidos los datos del tenant.
        // Fuera de desarrollo no tienen por qué estar (AUD-FE-019).
        devTools: __IS_DEV__,
        preloadedState: initialState,
        middleware: (getDefaultMiddleware) => getDefaultMiddleware({
            thunk: { extraArgument: extraArg },
        }),
    });

    // @ts-ignore  el manager se cuelga del store para los reducers dinámicos
    store.reducerManager = reducerManager;

    return store;
}

export type AppDispatch = ReturnType<typeof createReduxStore>['dispatch'];
