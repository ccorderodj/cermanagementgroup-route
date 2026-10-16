import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import type { OperatingState } from '../../types';

/**
 * Estados donde opera la compañía activa, con la sede principal primero.
 */
export const fetchOperatingStates = createAsyncThunk<OperatingState[], void, ThunkConfig<string>>(
    'regions/fetchOperatingStates',
    async (_, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.get<OperatingState[]>('/regions/operating');
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
