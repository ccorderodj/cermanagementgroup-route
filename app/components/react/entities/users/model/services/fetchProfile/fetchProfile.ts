import { createAsyncThunk } from '@reduxjs/toolkit';

import { ThunkConfig } from '@/app/providers/StoreProvider';
import { normalizeApiError, parseApi } from '@/shared/api';
import { userProfileSchema, UserProfile } from '../../types';

export const fetchProfile = createAsyncThunk<UserProfile, void, ThunkConfig<string>>(
    'users/fetchProfile',
    async (_, { extra, rejectWithValue }) => {
        try {
            const response = await extra.api.get('/auth/profile');
            return parseApi(userProfileSchema, response.data, 'fetchProfile');
        } catch (error) {
            return rejectWithValue(normalizeApiError(error).message);
        }
    },
);
