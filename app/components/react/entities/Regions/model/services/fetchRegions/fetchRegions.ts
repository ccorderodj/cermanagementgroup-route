import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { Region } from '../../types';
import { handleAsyncError } from '@/shared/lib/utils/utils';

export const fetchRegions = createAsyncThunk<Region[], void, ThunkConfig<string>>(
    'regions/fetchRegions',
    async (_, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;

        const requestUrl = '/regions';

        try {
            const response = await extra.api.get<Region[]>(requestUrl);

            if (!response.data) {
                throw new Error();
            }
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
