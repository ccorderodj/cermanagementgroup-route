import { createAsyncThunk } from '@reduxjs/toolkit';

import { ThunkConfig } from '@/app/providers/StoreProvider';
import { normalizeApiError, parseApi } from '@/shared/api';
import { userProfileSchema, UserProfile } from '../../types';

export interface UpdateProfilePayload {
    email: string;
    username: string;
    first_name: string;
    last_name: string;
    gender: boolean;
    new_password?: string | null;
}

export const updateProfile = createAsyncThunk<
    UserProfile,
    UpdateProfilePayload,
    ThunkConfig<string>
>(
    'users/updateProfile',
    async (payload, { extra, rejectWithValue }) => {
        try {
            const response = await extra.api.put('/auth/profile', payload);
            return parseApi(userProfileSchema, response.data, 'updateProfile');
        } catch (error) {
            return rejectWithValue(normalizeApiError(error).message);
        }
    },
);
