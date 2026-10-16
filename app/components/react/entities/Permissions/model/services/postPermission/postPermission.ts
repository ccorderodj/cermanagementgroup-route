import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { cleanPayload, handleAsyncError } from '@/shared/lib/utils/utils';
import { PermissionEntity } from '../../types';

interface IPostPermissionPayload {
    name: string;
    description?: string | null;
}

export const createPermission = createAsyncThunk<PermissionEntity, IPostPermissionPayload, ThunkConfig<string>>(
    'permissions/createPermission',
    async (payload, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.post<PermissionEntity>('/permissions', cleanPayload(payload));
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
