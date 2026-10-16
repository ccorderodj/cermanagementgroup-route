import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import { RoleEntity } from '../../types';

export const disableRole = createAsyncThunk<RoleEntity, number, ThunkConfig<string>>(
    'roles/disableRole',
    async (roleId, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.delete<RoleEntity>(`/roles/${roleId}`);
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
