import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { Company } from '../../types';
import { handleAsyncError } from '@/shared/lib/utils/utils';

export const fetchCompanies = createAsyncThunk<Company[], void, ThunkConfig<string>>(
    'companies/fetchCompanies',
    async (_, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;

        const requestUrl = '/companies';

        try {
            const response = await extra.api.get<Company[]>(requestUrl, {});

            if (!response.data) {
                throw new Error();
            }
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
