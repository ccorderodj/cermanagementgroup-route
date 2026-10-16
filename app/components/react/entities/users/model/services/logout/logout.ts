import { createAsyncThunk } from '@reduxjs/toolkit';

import { ThunkConfig } from '@/app/providers/StoreProvider';
import { normalizeApiError } from '@/shared/api';

/** Cierra la sesion. El servidor borra las cookies; aqui solo se limpia el store. */
export const logout = createAsyncThunk<void, void, ThunkConfig<string>>(
    'users/logout',
    async (_, { extra, rejectWithValue }) => {
        try {
            await extra.api.post('/public/auth/logout');
        } catch (error) {
            return rejectWithValue(normalizeApiError(error).message);
        }
        return undefined;
    },
);
