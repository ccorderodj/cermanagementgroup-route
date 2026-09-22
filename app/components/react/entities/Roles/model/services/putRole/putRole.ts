import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { cleanPayload, handleAsyncError } from '@/shared/lib/utils/utils';
import { RoleEntity } from '../../types';

interface IPutRolePayload {
    roleId: number;
    data: {
        name?: string;
        description?: string | null;
    };
}

export const updateRole = createAsyncThunk<RoleEntity, IPutRolePayload, ThunkConfig<string>>(
    'roles/updateRole',
    async ({ roleId, data }, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.put<RoleEntity>(`/roles/${roleId}`, cleanPayload(data));
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
