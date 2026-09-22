import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { cleanPayload, handleAsyncError } from '@/shared/lib/utils/utils';
import type { UserManagementEntity } from '../../types';

interface IPutUserManagementPayload {
    userId: number;
    data: {
        username?: string;
        email?: string | null;
        first_name?: string | null;
        last_name?: string | null;
        password?: string;
        gender?: boolean;
        /** Rol en la compañía activa; el backend actualiza user_company. */
        role_id?: number;
    };
}

/**
 * Actualiza los datos del usuario y su rol en la compañía activa.
 *
 * NO admite `is_active`: activar o suspender el acceso va por
 * `setUserAccess`, que escribe en la pertenencia (`user_company`) y no en la
 * identidad global (D7). El backend rechaza el campo si llega aquí.
 */
export const updateUserManagement = createAsyncThunk<UserManagementEntity, IPutUserManagementPayload, ThunkConfig<string>>(
    'userManagement/updateUserManagement',
    async ({ userId, data }, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.put<UserManagementEntity>(`/users/${userId}`, cleanPayload(data));
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
