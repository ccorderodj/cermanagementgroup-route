import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import type { RolePermissionsView } from '../../types';

interface IPutRolePermissionsPayload {
    roleId: number;
    permissionIds: number[];
}

/**
 * Reemplaza el conjunto de permisos del rol. Devuelve el catálogo al día.
 */
export const putRolePermissions = createAsyncThunk<RolePermissionsView, IPutRolePermissionsPayload, ThunkConfig<string>>(
    'roles/putRolePermissions',
    async ({ roleId, permissionIds }, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.put<RolePermissionsView>(
                `/roles/${roleId}/permissions`,
                { permission_ids: permissionIds },
            );
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
