import { createSlice } from '@reduxjs/toolkit';

import {
    clearIntegrationSecret,
    fetchCheckHistory,
    fetchPlatformDiagnostics,
    fetchPlatformReadiness,
    fetchPlatformSettings,
    runAllChecks,
    runCheck,
    saveIntegration,
    savePolicy,
    setIntegrationSecret,
    verifyIntegration,
} from '../services';
import type { Integration, PlatformSettingsSchema } from '../types';

const initialState: PlatformSettingsSchema = {
    integrations: [],
    policies: [],
    posture: [],
    readiness: undefined,
    checks: [],
    history: {},
    audit: [],
    isLoading: false,
    error: undefined,
};

function reemplazar(lista: Integration[], nueva: Integration): Integration[] {
    return lista.some((i) => i.key === nueva.key)
        ? lista.map((i) => (i.key === nueva.key ? nueva : i))
        : [...lista, nueva];
}

/**
 * Settings y Diagnostics comparten almacén.
 *
 * Verificar en Settings cambia el estado que Diagnostics enseña, y comprobar en
 * Diagnostics puede abrir un gate que Settings enseñaba cerrado. Con dos
 * almacenes, una de las dos pantallas enseñaría lo de hace un momento.
 *
 * Los errores de las escrituras no se guardan aquí: los recoge quien actúa y los
 * enseña junto al botón que falló. Aquí sólo va el error de carga.
 */
export const platformSettingsSlice = createSlice({
    name: 'platformSettingsSlice',
    initialState,
    reducers: {},
    extraReducers: (builder) => {
        builder
            .addCase(fetchPlatformSettings.pending, (state) => {
                state.isLoading = true;
                state.error = undefined;
            })
            .addCase(fetchPlatformSettings.fulfilled, (state, action) => {
                state.isLoading = false;
                state.integrations = action.payload.integrations;
                state.policies = action.payload.policies;
                state.posture = action.payload.posture;
                state.readiness = action.payload.readiness;
                state.audit = action.payload.audit;
            })
            .addCase(fetchPlatformSettings.rejected, (state, action) => {
                state.isLoading = false;
                state.error = action.payload ?? 'Could not load platform settings.';
            })

            .addCase(fetchPlatformDiagnostics.pending, (state) => {
                state.isLoading = true;
                state.error = undefined;
            })
            .addCase(fetchPlatformDiagnostics.fulfilled, (state, action) => {
                state.isLoading = false;
                state.checks = action.payload.checks;
                state.readiness = action.payload.readiness;
            })
            .addCase(fetchPlatformDiagnostics.rejected, (state, action) => {
                state.isLoading = false;
                state.error = action.payload ?? 'Could not load diagnostics.';
            })

            .addCase(fetchPlatformReadiness.fulfilled, (state, action) => {
                state.readiness = action.payload;
            })

            .addCase(saveIntegration.fulfilled, (state, action) => {
                state.integrations = reemplazar(state.integrations, action.payload.integration);
                state.readiness = action.payload.readiness;
            })
            .addCase(setIntegrationSecret.fulfilled, (state, action) => {
                state.integrations = reemplazar(state.integrations, action.payload.integration);
                state.readiness = action.payload.readiness;
            })
            .addCase(clearIntegrationSecret.fulfilled, (state, action) => {
                state.integrations = reemplazar(state.integrations, action.payload.integration);
                state.readiness = action.payload.readiness;
            })
            .addCase(verifyIntegration.fulfilled, (state, action) => {
                state.integrations = reemplazar(state.integrations, action.payload.integration);
                state.readiness = action.payload.readiness;
                const { check } = action.payload;
                state.history[check.capability_key] = [check, ...(state.history[check.capability_key] ?? [])];
            })
            .addCase(savePolicy.fulfilled, (state, action) => {
                state.policies = state.policies.map(
                    (p) => (p.key === action.payload.policy.key ? action.payload.policy : p),
                );
                state.readiness = action.payload.readiness;
            })

            .addCase(runAllChecks.fulfilled, (state, action) => {
                state.checks = action.payload.checks;
                state.readiness = action.payload.readiness;
                // El historial abierto ya no es el último; se vuelve a pedir.
                state.history = {};
            })
            .addCase(runCheck.fulfilled, (state, action) => {
                state.checks = action.payload.checks;
                state.readiness = action.payload.readiness;
                state.history = {};
            })
            .addCase(fetchCheckHistory.fulfilled, (state, action) => {
                state.history[action.payload.key] = action.payload.runs;
            });
    },
});

export const { reducer: platformSettingsSliceReducer } = platformSettingsSlice;
