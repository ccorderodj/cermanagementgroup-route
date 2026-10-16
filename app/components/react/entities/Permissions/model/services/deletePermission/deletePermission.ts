import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import { PermissionEntity } from '../../types';

export const disablePermission = createAsyncThunk<PermissionEntity, number, ThunkConfig<string>>(
    'permissions/disablePermission',
    async (permissionId, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.delete<PermissionEntity>(`/permissions/${permissionId}`);
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
