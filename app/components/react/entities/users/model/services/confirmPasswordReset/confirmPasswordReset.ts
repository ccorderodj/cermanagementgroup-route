import { createAsyncThunk } from '@reduxjs/toolkit';

import { ThunkConfig } from '@/app/providers/StoreProvider';
import { normalizeApiError, parseApi } from '@/shared/api';
import { authAckSchema, AuthAck, PasswordResetConfirmPayload } from '../../types';

/** Canjea el enlace por una contrasena nueva. El enlace queda inutilizable. */
export const confirmPasswordReset = createAsyncThunk<
    AuthAck,
    PasswordResetConfirmPayload,
    ThunkConfig<string>
>(
    'users/confirmPasswordReset',
    async (payload, { extra, rejectWithValue }) => {
        try {
            const response = await extra.api.post(
                '/public/auth/password-reset/confirm',
                payload,
            );
            return parseApi(authAckSchema, response.data, 'confirmPasswordReset');
        } catch (error) {
            return rejectWithValue(normalizeApiError(error).message);
        }
    },
);
