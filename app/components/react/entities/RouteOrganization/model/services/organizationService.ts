import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { parseApi } from '@/shared/api';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import {
    orgOptionsSchema,
    successionInfoSchema,
    successionPlanSchema,
    type OrgOptions,
    type SuccessionInfo,
    type SuccessionPlan,
} from '../types';

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

/** Qué pasaría al retirar a esta persona y quién puede sustituirla. No escribe. */
export const fetchSuccession = createAsyncThunk<SuccessionInfo, number, ThunkConfig<string>>(
    'routeOrganization/fetchSuccession',
    async (userId, { extra, rejectWithValue }) => {
        try {
            const response = await extra.api.get(`${BASE}/${userId}/succession`);
            return parseApi(successionInfoSchema, response.data, 'fetchSuccession');
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);

export interface SuccessionRequest {
    operation: 'retire' | 'replace';
    userId: number;
    successorUserId?: number;
    version?: number;
    reason?: string;
    /** `true`: sólo la vista previa, sin escribir nada. */
    dryRun: boolean;
    /** V1.6, sólo al sustituir: quien sale se queda con este rol inferior… */
    outgoingRoleId?: number;
    /** …y bajo esta persona. */
    outgoingSuperiorUserId?: number;
}

/** Retira o sustituye a un responsable; con `dryRun`, sólo calcula el plan. */
export const runSuccession = createAsyncThunk<SuccessionPlan, SuccessionRequest, ThunkConfig<string>>(
    'routeOrganization/runSuccession',
    async ({
        operation, userId, successorUserId, version, reason, dryRun, outgoingRoleId, outgoingSuperiorUserId,
    }, { extra, rejectWithValue }) => {
        try {
            const response = await extra.api.post(`${BASE}/${userId}/${operation}`, {
                successor_user_id: successorUserId,
                version,
                reason: reason || undefined,
                dry_run: dryRun,
                outgoing_role_id: outgoingRoleId,
                outgoing_superior_user_id: outgoingSuperiorUserId,
            });
            return parseApi(successionPlanSchema, response.data, 'runSuccession');
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
