import { createAsyncThunk } from '@reduxjs/toolkit';

import { ThunkConfig } from '@/app/providers/StoreProvider';
import {
    LOGIN_ENDPOINT, normalizeApiError, parseApi, type ApiError,
} from '@/shared/api';
import { authAckSchema, AuthAck, LoginPayload } from '../../types';

/**
 * Pide de nuevo la página actual para que el servidor vuelva a emitir sus
 * cookies (`cer_csrf_token` y `app_data`).
 *
 * Una pestaña restaurada por el móvil días después —sin volver a pedirse al
 * servidor— o un navegador que borró sus cookies enseña el formulario, pero sin
 * el testigo CSRF el login se rechaza con 403 antes de mirar las credenciales
 * (incidente 19-10-2026). Las páginas son GET: no necesitan testigo y lo emiten.
 */
async function renovarCookies(): Promise<void> {
    await fetch(window.location.pathname + window.location.search, {
        credentials: 'same-origin',
        cache: 'no-store',
    });
}

const esCsrf = (e: ApiError) => e.status === 403 && (e.code === 'csrf_missing' || e.code === 'csrf_mismatch');

/**
 * Lo que la pantalla dice de cada fallo. El servidor responde igual a «no
 * existe» y a «contraseña incorrecta» (a propósito), pero el resto de fallos no
 * son de credenciales y no deben parecerlo.
 */
export function mensajeDeLogin(e: ApiError): string {
    if (e.status === null) return 'Could not reach the server. Check your connection and try again.';
    if (esCsrf(e)) return 'This page is out of date. Reload the page and sign in again.';
    if (e.status === 422) return 'Enter your full email address (name@company.com) and your password.';
    if (e.status >= 500) return 'The server is not available right now. Try again in a few minutes.';
    return e.message;
}

/**
 * Inicio de sesion.
 *
 * Va por el router publico —es el unico endpoint que puede usarse sin sesion—
 * y la respuesta **no trae el token**: la sesion queda en una cookie HttpOnly
 * que el servidor emite. Devolverlo tambien en el cuerpo, como hacia antes,
 * anulaba el motivo de marcarla HttpOnly (AUD-SEC-017).
 *
 * Si falta el testigo CSRF, se renuevan las cookies y se reintenta **una vez**.
 */
export const login = createAsyncThunk<AuthAck, LoginPayload, ThunkConfig<string>>(
    'users/login',
    async (payload, { extra, rejectWithValue }) => {
        const intentar = async () => {
            const response = await extra.api.post(LOGIN_ENDPOINT, payload);
            return parseApi(authAckSchema, response.data, 'login');
        };
        try {
            return await intentar();
        } catch (error) {
            const primero = normalizeApiError(error);
            if (!esCsrf(primero)) return rejectWithValue(mensajeDeLogin(primero));
            try {
                await renovarCookies();
                return await intentar();
            } catch (otro) {
                return rejectWithValue(mensajeDeLogin(normalizeApiError(otro)));
            }
        }
    },
);
