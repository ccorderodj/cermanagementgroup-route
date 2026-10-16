import { createAsyncThunk } from '@reduxjs/toolkit';
import { z } from 'zod';

import { ThunkConfig } from '@/app/providers/StoreProvider';
import { normalizeApiError, parseApi } from '@/shared/api';
import {
    checkRunSchema,
    checkSchema,
    integrationSchema,
    platformAuditSchema,
    policySchema,
    postureItemSchema,
    readinessSchema,
    verifyResultSchema,
    type Check,
    type CheckRun,
    type Integration,
    type PlatformAudit,
    type Policy,
    type PostureItem,
    type Readiness,
} from '../types';

/**
 * La API de plataforma. Sólo administración de plataforma.
 *
 * Toda escritura devuelve también la preparación recién calculada: guardar una
 * credencial abre el gate que estaba cerrado, y la franja de arriba tiene que
 * decirlo en el mismo repintado, no al recargar.
 */

/** El servidor rechaza con una lista de frases (qué falta) o con una. Se
 *  enseñan todas: el motivo es justo lo que la persona necesita leer. */
function detailMessage(error: unknown): string {
    const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
    if (Array.isArray(detail) && detail.every((d) => typeof d === 'string')) {
        return detail.join(' ');
    }
    return normalizeApiError(error).message;
}

const PLATFORM = '/platform';

async function getReadiness(api: ThunkConfig<string>['extra']['api']): Promise<Readiness> {
    const response = await api.get(`${PLATFORM}/readiness`);
    return parseApi(readinessSchema, response.data, 'platformReadiness');
}

export const fetchPlatformReadiness = createAsyncThunk<Readiness, void, ThunkConfig<string>>(
    'platformSettings/fetchReadiness',
    async (_, { extra, rejectWithValue }) => {
        try {
            return await getReadiness(extra.api);
        } catch (error) {
            return rejectWithValue(detailMessage(error));
        }
    },
);

export interface PlatformSettingsPayload {
    integrations: Integration[];
    policies: Policy[];
    posture: PostureItem[];
    readiness: Readiness;
    audit: PlatformAudit[];
}

export const fetchPlatformSettings = createAsyncThunk<
PlatformSettingsPayload,
void,
ThunkConfig<string>
>('platformSettings/fetchSettings', async (_, { extra, rejectWithValue }) => {
    try {
        const [integraciones, politicas, postura, preparacion, traza] = await Promise.all([
            extra.api.get(`${PLATFORM}/integrations`),
            extra.api.get(`${PLATFORM}/policies`),
            extra.api.get(`${PLATFORM}/posture`),
            getReadiness(extra.api),
            extra.api.get(`${PLATFORM}/audit`, { params: { limit: 20 } }),
        ]);
        return {
            integrations: parseApi(z.array(integrationSchema), integraciones.data, 'platformIntegrations'),
            policies: parseApi(z.array(policySchema), politicas.data, 'platformPolicies'),
            posture: parseApi(z.array(postureItemSchema), postura.data, 'platformPosture'),
            readiness: preparacion,
            audit: parseApi(z.array(platformAuditSchema), traza.data, 'platformAudit'),
        };
    } catch (error) {
        return rejectWithValue(detailMessage(error));
    }
});

export interface IntegrationChange {
    integration: Integration;
    readiness: Readiness;
}

export const saveIntegration = createAsyncThunk<
IntegrationChange,
{ key: string; provider: string; config: Record<string, string | number | boolean>; enabled: boolean; expectedVersion: number },
ThunkConfig<string>
>('platformSettings/saveIntegration', async (arg, { extra, rejectWithValue }) => {
    try {
        const response = await extra.api.put(`${PLATFORM}/integrations/${arg.key}`, {
            provider: arg.provider,
            config: arg.config,
            enabled: arg.enabled,
            expected_version: arg.expectedVersion,
        });
        return {
            integration: parseApi(integrationSchema, response.data, 'saveIntegration'),
            readiness: await getReadiness(extra.api),
        };
    } catch (error) {
        return rejectWithValue(detailMessage(error));
    }
});

export const setIntegrationSecret = createAsyncThunk<
IntegrationChange,
{ key: string; name: string; value: string; expiresAt?: string },
ThunkConfig<string>
>('platformSettings/setSecret', async (arg, { extra, rejectWithValue }) => {
    try {
        const response = await extra.api.put(`${PLATFORM}/integrations/${arg.key}/secrets/${arg.name}`, {
            value: arg.value,
            expires_at: arg.expiresAt || null,
        });
        return {
            integration: parseApi(integrationSchema, response.data, 'setIntegrationSecret'),
            readiness: await getReadiness(extra.api),
        };
    } catch (error) {
        return rejectWithValue(detailMessage(error));
    }
});

export const clearIntegrationSecret = createAsyncThunk<
IntegrationChange,
{ key: string; name: string },
ThunkConfig<string>
>('platformSettings/clearSecret', async (arg, { extra, rejectWithValue }) => {
    try {
        const response = await extra.api.delete(`${PLATFORM}/integrations/${arg.key}/secrets/${arg.name}`);
        return {
            integration: parseApi(integrationSchema, response.data, 'clearIntegrationSecret'),
            readiness: await getReadiness(extra.api),
        };
    } catch (error) {
        return rejectWithValue(detailMessage(error));
    }
});

export interface VerifyChange extends IntegrationChange {
    check: CheckRun;
}

export const verifyIntegration = createAsyncThunk<VerifyChange, string, ThunkConfig<string>>(
    'platformSettings/verifyIntegration',
    async (key, { extra, rejectWithValue }) => {
        try {
            const response = await extra.api.post(`${PLATFORM}/integrations/${key}/verify`);
            const resultado = parseApi(verifyResultSchema, response.data, 'verifyIntegration');
            return { ...resultado, readiness: await getReadiness(extra.api) };
        } catch (error) {
            return rejectWithValue(detailMessage(error));
        }
    },
);

export const sendTestEmail = createAsyncThunk<
{ to: string },
{ key: string; to: string },
ThunkConfig<string>
>(
    'platformSettings/sendTestEmail',
    async (arg, { extra, rejectWithValue }) => {
        try {
            await extra.api.post(`${PLATFORM}/integrations/${arg.key}/test-message`, { to: arg.to });
            return { to: arg.to };
        } catch (error) {
            return rejectWithValue(detailMessage(error));
        }
    },
);

export const savePolicy = createAsyncThunk<
{ policy: Policy; readiness: Readiness },
{ key: string; value: Record<string, unknown>; expectedVersion: number },
ThunkConfig<string>
>('platformSettings/savePolicy', async (arg, { extra, rejectWithValue }) => {
    try {
        const response = await extra.api.put(`${PLATFORM}/policies/${arg.key}`, {
            value: arg.value,
            expected_version: arg.expectedVersion,
        });
        return {
            policy: parseApi(policySchema, response.data, 'savePolicy'),
            readiness: await getReadiness(extra.api),
        };
    } catch (error) {
        return rejectWithValue(detailMessage(error));
    }
});

export interface DiagnosticsPayload {
    checks: Check[];
    readiness: Readiness;
}

async function getDiagnostics(api: ThunkConfig<string>['extra']['api']): Promise<DiagnosticsPayload> {
    const [comprobaciones, preparacion] = await Promise.all([
        api.get(`${PLATFORM}/diagnostics`),
        getReadiness(api),
    ]);
    return {
        checks: parseApi(z.array(checkSchema), comprobaciones.data, 'platformDiagnostics'),
        readiness: preparacion,
    };
}

export const fetchPlatformDiagnostics = createAsyncThunk<DiagnosticsPayload, void, ThunkConfig<string>>(
    'platformSettings/fetchDiagnostics',
    async (_, { extra, rejectWithValue }) => {
        try {
            return await getDiagnostics(extra.api);
        } catch (error) {
            return rejectWithValue(detailMessage(error));
        }
    },
);

/** Comprobar ahora. Devuelve el panorama recién leído, no lo que la pantalla
 *  cree recordar: una comprobación puede cambiar el estado de otra fila. */
export const runAllChecks = createAsyncThunk<DiagnosticsPayload, void, ThunkConfig<string>>(
    'platformSettings/runAllChecks',
    async (_, { extra, rejectWithValue }) => {
        try {
            await extra.api.post(`${PLATFORM}/diagnostics/run-all`);
            return await getDiagnostics(extra.api);
        } catch (error) {
            return rejectWithValue(detailMessage(error));
        }
    },
);

export const runCheck = createAsyncThunk<DiagnosticsPayload, string, ThunkConfig<string>>(
    'platformSettings/runCheck',
    async (key, { extra, rejectWithValue }) => {
        try {
            await extra.api.post(`${PLATFORM}/diagnostics/${key}/run`);
            return await getDiagnostics(extra.api);
        } catch (error) {
            return rejectWithValue(detailMessage(error));
        }
    },
);

export const fetchCheckHistory = createAsyncThunk<
{ key: string; runs: CheckRun[] },
string,
ThunkConfig<string>
>('platformSettings/fetchHistory', async (key, { extra, rejectWithValue }) => {
    try {
        const response = await extra.api.get(`${PLATFORM}/diagnostics/${key}/history`, { params: { limit: 25 } });
        return { key, runs: parseApi(z.array(checkRunSchema), response.data, 'checkHistory') };
    } catch (error) {
        return rejectWithValue(detailMessage(error));
    }
});
