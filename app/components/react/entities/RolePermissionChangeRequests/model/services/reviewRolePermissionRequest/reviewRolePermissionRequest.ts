import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import type { RolePermissionChangeRequestEntity } from '../../types';

interface IReviewPayload {
    requestId: number;
    note?: string;
}

/**
 * Aprueba la solicitud: aplica el cambio de permisos.
 * Solo roles de gestión, y nunca quien la envió.
 */
export const approveRolePermissionRequest = createAsyncThunk<
    RolePermissionChangeRequestEntity, IReviewPayload, ThunkConfig<string>
>(
    'rolePermissionRequests/approve',
    async ({ requestId }, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.post<RolePermissionChangeRequestEntity>(
                `/rolepermissionsapprovals/${requestId}/approve`,
            );
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);

/** Rechaza la solicitud sin aplicarla. */
export const rejectRolePermissionRequest = createAsyncThunk<
    RolePermissionChangeRequestEntity, IReviewPayload, ThunkConfig<string>
>(
    'rolePermissionRequests/reject',
    async ({ requestId, note }, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.post<RolePermissionChangeRequestEntity>(
                `/rolepermissionsapprovals/${requestId}/reject`,
                { review_note: note ?? null },
            );
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
