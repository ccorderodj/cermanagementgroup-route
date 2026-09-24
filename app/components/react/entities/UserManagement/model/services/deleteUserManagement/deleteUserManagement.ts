import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { handleAsyncError } from '@/shared/lib/utils/utils';

interface IDeleteUserPayload {
    userId: number;
}

/**
 * Retira a la persona de **esta** compañía.
 *
 * No es `setUserAccess({ isActive: false })`. Suspender corta el acceso y deja
 * al usuario en la administración, listo para restaurarse; esto lo saca de la
 * experiencia normal del tenant.
 *
 * Lo que **no** hace: destruir la identidad. `user` puede pertenecer a otras
 * compañías y al plano de plataforma, así que lo que se borra es la
 * pertenencia — quien administra este tenant no tiene autoridad sobre lo demás.
 *
 * Devuelve el id retirado para que el panel pueda quitar la fila sin esperar a
 * recargar: el servidor responde 204 y no hay cuerpo que devolver.
 */
export const deleteUserManagement = createAsyncThunk<number, IDeleteUserPayload, ThunkConfig<string>>(
    'userManagement/deleteUser',
    async ({ userId }, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            await extra.api.delete(`/users/${userId}`);
            return userId;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
