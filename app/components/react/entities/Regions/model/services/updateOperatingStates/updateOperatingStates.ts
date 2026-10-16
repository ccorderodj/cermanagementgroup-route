import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import type { OperatingState } from '../../types';

/**
 * Reemplaza el conjunto de estados donde opera la compañía activa.
 */
export const updateOperatingStates = createAsyncThunk<
OperatingState[],
number[],
ThunkConfig<string>
>(
    'regions/updateOperatingStates',
    async (stateIds, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.put<OperatingState[]>('/regions/operating', {
                state_ids: stateIds,
            });
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
