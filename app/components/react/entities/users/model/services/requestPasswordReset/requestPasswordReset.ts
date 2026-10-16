import { createAsyncThunk } from '@reduxjs/toolkit';

import { ThunkConfig } from '@/app/providers/StoreProvider';
import { normalizeApiError, parseApi } from '@/shared/api';
import { authAckSchema, AuthAck, PasswordResetRequestPayload } from '../../types';

/**
 * Pide el enlace de recuperacion.
 *
 * La respuesta es la misma exista o no la cuenta, asi que la pantalla debe
 * mostrar siempre el mismo mensaje: cualquier diferencia visible convertiria
 * el formulario en un comprobador de direcciones.
 */
export const requestPasswordReset = createAsyncThunk<
    AuthAck,
    PasswordResetRequestPayload,
    ThunkConfig<string>
>(
    'users/requestPasswordReset',
    async (payload, { extra, rejectWithValue }) => {
        try {
            const response = await extra.api.post('/public/auth/password-reset', payload);
            return parseApi(authAckSchema, response.data, 'requestPasswordReset');
        } catch (error) {
            return rejectWithValue(normalizeApiError(error).message);
        }
    },
);
