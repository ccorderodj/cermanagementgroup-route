import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import type { RolePermissionsView } from '../../types';

/**
 * Catálogo completo de permisos con los del rol ya marcados.
 */
export const fetchRolePermissions = createAsyncThunk<RolePermissionsView, number, ThunkConfig<string>>(
    'roles/fetchRolePermissions',
    async (roleId, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.get<RolePermissionsView>(`/roles/${roleId}/permissions`);
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
