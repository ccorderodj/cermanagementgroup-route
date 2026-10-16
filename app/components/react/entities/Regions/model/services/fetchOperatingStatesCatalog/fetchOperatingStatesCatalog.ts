import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { handleAsyncError } from '@/shared/lib/utils/utils';
import type { OperatingStateCatalogItem } from '../../types';

/**
 * Catálogo completo de estados de EE.UU., marcando cuáles opera la compañía.
 */
export const fetchOperatingStatesCatalog = createAsyncThunk<
OperatingStateCatalogItem[],
void,
ThunkConfig<string>
>(
    'regions/fetchOperatingStatesCatalog',
    async (_, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.get<OperatingStateCatalogItem[]>('/regions/catalog');
            if (!response.data) throw new Error();
            return response.data;
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
