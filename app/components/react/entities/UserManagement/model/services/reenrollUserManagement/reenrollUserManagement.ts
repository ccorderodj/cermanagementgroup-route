import { createAsyncThunk } from '@reduxjs/toolkit';
import type { AxiosError } from 'axios';
import { $api } from '@/shared/api';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import { contractBasePath, type UserManagementContract } from '../contract';
import type { UserManagementEntity } from '../../types';

/**
 * Devuelve el acceso a quien ya estuvo en esta compañía.
 *
 * Endpoint **aparte** de crear, y a propósito: readmitir tiene que ser una
 * decisión explícita. Crear devuelve el conflicto con su código, la pantalla
 * pide confirmación, y sólo entonces se llama aquí. Un `create` que readmitiera
 * al detectar la historia sería el restablecimiento silencioso que la
 * instrucción prohíbe.
 *
 * Sólo viajan el rol y, con un rol de la jerarquía, a quién reporta (V1.4).
 * La identidad ya existe y no se vuelve a describir: ni nombre, ni correo, ni
 * contraseña — quien vuelve entra con la credencial que ya tenía.
 */
export const reenrollUserManagement = createAsyncThunk<
    UserManagementEntity,
    { userId: number; roleId: number; superiorUserId?: number; contract?: UserManagementContract },
    { rejectValue: unknown }
>(
    'userManagement/reenroll',
    async ({ userId, roleId, superiorUserId, contract }, thunkApi) => {
        const { rejectWithValue } = thunkApi;
        try {
            const response = await $api.post(
                `${contractBasePath(contract)}/${userId}/reenrollment`,
                superiorUserId != null
                    ? { role_id: roleId, superior_user_id: superiorUserId }
                    : { role_id: roleId },
            );
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
