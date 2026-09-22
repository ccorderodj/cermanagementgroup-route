import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import type { FeatureMapItem } from '../../types';

/** Mapa de capacidades del sistema, con los roles que tienen cada una. */
export const fetchFeatureMap = createAsyncThunk<FeatureMapItem[], void, ThunkConfig<string>>(
    'permissions/fetchFeatureMap',
    async (_, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.get<FeatureMapItem[]>('/permissions/feature-map');
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
