import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { contractBasePath, type UserManagementContract } from '../contract';
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
    /**
     * Desde qué producto se administra. No viaja en el cuerpo: decide **a qué
     * ruta** se envía, y con ello qué roles acepta el servidor.
     */
    contract?: UserManagementContract;
}

export const createUserManagement = createAsyncThunk<UserManagementEntity, IPostUserManagementPayload, ThunkConfig<string>>(
    'userManagement/createUserManagement',
    async (payload, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const { contract, ...datos } = payload;
            const response = await extra.api.post<UserManagementEntity>(
                contractBasePath(contract),
                cleanPayload(datos),
            );
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
