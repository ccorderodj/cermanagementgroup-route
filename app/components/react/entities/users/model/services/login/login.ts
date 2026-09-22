import { createAsyncThunk } from '@reduxjs/toolkit';

import { ThunkConfig } from '@/app/providers/StoreProvider';
import { normalizeApiError, parseApi } from '@/shared/api';
import { authAckSchema, AuthAck, LoginPayload } from '../../types';

/**
 * Inicio de sesion.
 *
 * Va por el router publico —es el unico endpoint que puede usarse sin sesion—
 * y la respuesta **no trae el token**: la sesion queda en una cookie HttpOnly
 * que el servidor emite. Devolverlo tambien en el cuerpo, como hacia antes,
 * anulaba el motivo de marcarla HttpOnly (AUD-SEC-017).
 */
export const login = createAsyncThunk<AuthAck, LoginPayload, ThunkConfig<string>>(
    'users/login',
    async (payload, { extra, rejectWithValue }) => {
        try {
            const response = await extra.api.post('/public/auth/login', payload);
            return parseApi(authAckSchema, response.data, 'login');
        } catch (error) {
            return rejectWithValue(normalizeApiError(error).message);
        }
    },
);
