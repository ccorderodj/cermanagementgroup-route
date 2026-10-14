import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { parseApi } from '@/shared/api';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import { orgOptionsSchema, type OrgOptions } from '../types';

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
