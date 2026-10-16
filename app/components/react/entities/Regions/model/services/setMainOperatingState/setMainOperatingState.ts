import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import type { OperatingState } from '../../types';

/**
 * Marca un estado activo como la sede principal de la compañía.
 */
export const setMainOperatingState = createAsyncThunk<
OperatingState[],
number,
ThunkConfig<string>
>(
    'regions/setMainOperatingState',
    async (stateId, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.put<OperatingState[]>('/regions/operating/main', {
                state_id: stateId,
            });
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
