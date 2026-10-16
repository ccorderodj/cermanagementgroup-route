import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { cleanPayload, handleAsyncError } from '@/shared/lib/utils/utils';
import { PermissionEntity } from '../../types';

interface IPutPermissionPayload {
    permissionId: number;
    data: {
        name?: string;
        description?: string | null;
    };
}

export const updatePermission = createAsyncThunk<PermissionEntity, IPutPermissionPayload, ThunkConfig<string>>(
    'permissions/updatePermission',
    async ({ permissionId, data }, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.put<PermissionEntity>(`/permissions/${permissionId}`, cleanPayload(data));
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
