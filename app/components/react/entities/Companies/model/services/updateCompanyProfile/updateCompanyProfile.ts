import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import { CompanyProfile } from '../../types';

export type UpdateCompanyProfilePayload =
    Pick<CompanyProfile, 'name'>
    & Partial<Omit<CompanyProfile, 'id' | 'name'>>;

export const updateCompanyProfile = createAsyncThunk<
CompanyProfile,
UpdateCompanyProfilePayload,
ThunkConfig<string>
>(
    'companies/updateCompanyProfile',
    async (payload, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.put<CompanyProfile>('/companies/profile', payload);
            if (!response.data) {
                throw new Error();
            }
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
