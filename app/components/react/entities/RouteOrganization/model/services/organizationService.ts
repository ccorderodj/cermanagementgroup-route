import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { parseApi } from '@/shared/api';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import { orgAssignmentSchema, orgOptionsSchema, type OrgAssignment, type OrgOptions } from '../types';

const BASE = '/route/organization';

/** Cargos y superiores que **quien está autenticado** puede asignar a esta persona. */
export const fetchOrgOptions = createAsyncThunk<OrgOptions, number | undefined, ThunkConfig<string>>(
    'routeOrganization/fetchOrgOptions',
    async (userId, { extra, rejectWithValue }) => {
        try {
            const response = await extra.api.get(`${BASE}/options`, {
                params: userId != null ? { user_id: userId } : {},
            });
            return parseApi(orgOptionsSchema, response.data, 'fetchOrgOptions');
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);

/** Fija el cargo y el superior vigentes. `version`: la vista (0 si no tenía). */
export const putOrgAssignment = createAsyncThunk<
    OrgAssignment,
    { userId: number; position: string; superiorUserId: number | null; version: number },
    ThunkConfig<string>
>(
    'routeOrganization/putOrgAssignment',
    async ({ userId, position, superiorUserId, version }, { extra, rejectWithValue }) => {
        try {
            const response = await extra.api.put(`${BASE}/${userId}`, {
                position,
                superior_user_id: superiorUserId,
                version,
            });
            return parseApi(orgAssignmentSchema, response.data, 'putOrgAssignment');
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);

/** Quita el cargo vigente. */
export const deleteOrgAssignment = createAsyncThunk<
    void,
    { userId: number; version: number },
    ThunkConfig<string>
>(
    'routeOrganization/deleteOrgAssignment',
    async ({ userId, version }, { extra, rejectWithValue }) => {
        try {
            await extra.api.delete(`${BASE}/${userId}`, { params: { version } });
            return undefined;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
