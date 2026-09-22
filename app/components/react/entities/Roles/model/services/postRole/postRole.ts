import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { cleanPayload, handleAsyncError } from '@/shared/lib/utils/utils';
import { RoleEntity } from '../../types';

interface IPostRolePayload {
    name: string;
    description?: string | null;
}

export const createRole = createAsyncThunk<RoleEntity, IPostRolePayload, ThunkConfig<string>>(
    'roles/createRole',
    async (payload, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.post<RoleEntity>('/roles', cleanPayload(payload));
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
