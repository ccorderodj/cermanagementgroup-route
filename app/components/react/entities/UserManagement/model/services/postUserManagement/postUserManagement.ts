import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { cleanPayload, handleAsyncError } from '@/shared/lib/utils/utils';
import type { UserManagementEntity } from '../../types';

interface IPostUserManagementPayload {
    username: string;
    email: string;
    first_name: string;
    last_name: string;
    password: string;
    gender?: boolean;
    role_id: number;
}

export const createUserManagement = createAsyncThunk<UserManagementEntity, IPostUserManagementPayload, ThunkConfig<string>>(
    'userManagement/createUserManagement',
    async (payload, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.post<UserManagementEntity>('/users', cleanPayload(payload));
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
