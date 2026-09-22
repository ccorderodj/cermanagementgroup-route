import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { regionsPaginationSliceActions } from '../../slice/regionsPaginationSlice';
import { fetchRegionsPagination } from '../fetchRegionsPagination/fetchRegionsPagination';

export const fetchRegionsPageSize = createAsyncThunk<void, number, ThunkConfig<string>>(
    'regions/fetchRegionsPageSize',
    async (pageSize, thunkApi) => {
        const { dispatch } = thunkApi;
        dispatch(regionsPaginationSliceActions.setPageSize(pageSize));
        dispatch(regionsPaginationSliceActions.setIndexPage(0));
        dispatch(fetchRegionsPagination({}));
    },
);
