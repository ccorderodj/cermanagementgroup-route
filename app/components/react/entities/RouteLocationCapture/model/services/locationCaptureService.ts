import { $api, parseApi } from '@/shared/api';
import { captureSettingSchema, type CaptureSetting } from '../types';

export async function fetchCaptureSetting(): Promise<CaptureSetting> {
    const response = await $api.get('/location-capture/settings');
    return parseApi(captureSettingSchema, response.data, 'fetchCaptureSetting');
}

/** Guarda. 409 si otra persona guardó desde que se leyó (`version`). */
export async function updateCaptureSetting(input: {
    enabled: boolean;
    interval_seconds: number;
    version: number;
}): Promise<CaptureSetting> {
    const response = await $api.put('/location-capture/settings', input);
    return parseApi(captureSettingSchema, response.data, 'updateCaptureSetting');
}
