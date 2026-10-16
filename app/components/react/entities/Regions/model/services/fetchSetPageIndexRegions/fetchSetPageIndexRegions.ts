import { createAsyncThunk } from '@reduxjs/toolkit';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { regionsPaginationSliceActions } from '../../slice/regionsPaginationSlice';
import { fetchRegionsPagination } from '../fetchRegionsPagination/fetchRegionsPagination';

export const fetchSetPageIndexRegions = createAsyncThunk<void, number, ThunkConfig<string>>(
    'employees/fetchSetPageIndexRegions',
    async (pageIndex, thunkApi) => {
        const { dispatch } = thunkApi;
        dispatch(regionsPaginationSliceActions.setIndexPage(pageIndex));
        dispatch(fetchRegionsPagination({}));
    },
);
