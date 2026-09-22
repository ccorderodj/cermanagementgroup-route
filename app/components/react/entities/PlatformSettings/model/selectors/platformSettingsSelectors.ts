import { StateSchema } from '@/app/providers/StoreProvider';

export const getPlatformIntegrations = (s: StateSchema) => s.platformSettings?.integrations ?? [];
export const getPlatformPolicies = (s: StateSchema) => s.platformSettings?.policies ?? [];
export const getPlatformPosture = (s: StateSchema) => s.platformSettings?.posture ?? [];

/** El veredicto del servidor. No se recalcula aquí. */
export const getPlatformReadiness = (s: StateSchema) => s.platformSettings?.readiness;

export const getPlatformChecks = (s: StateSchema) => s.platformSettings?.checks ?? [];
export const getPlatformCheckHistory = (s: StateSchema) => s.platformSettings?.history ?? {};
export const getPlatformAudit = (s: StateSchema) => s.platformSettings?.audit ?? [];
export const getPlatformSettingsIsLoading = (s: StateSchema) => s.platformSettings?.isLoading ?? false;
export const getPlatformSettingsError = (s: StateSchema) => s.platformSettings?.error;
