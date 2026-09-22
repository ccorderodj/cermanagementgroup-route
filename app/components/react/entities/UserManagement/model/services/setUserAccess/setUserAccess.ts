import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import type { UserManagementEntity } from '../../types';

interface ISetUserAccessPayload {
    userId: number;
    isActive: boolean;
}

/**
 * Activa o suspende el acceso de un usuario sin borrarlo.
 */
export const setUserAccess = createAsyncThunk<UserManagementEntity, ISetUserAccessPayload, ThunkConfig<string>>(
    'userManagement/setUserAccess',
    async ({ userId, isActive }, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.put<UserManagementEntity>(
                `/users/${userId}/access`,
                { is_active: isActive },
            );
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
