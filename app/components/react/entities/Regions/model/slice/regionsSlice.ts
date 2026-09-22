import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import {
    fetchRegions,
} from '../services';
import {
    Region,
    RegionsSchema,
} from '../types';

const initialState: RegionsSchema = {
    isLoading: false,
    error: undefined,
    data: [],
};

export const regionsSlice = createSlice({
    name: 'regionsSlice',
    initialState,
    reducers: {
        setRegionIds: (state, action: PayloadAction<number[]>) => {
            state.region_ids = action.payload;
        },
        setRegionId: (state, action: PayloadAction<number>) => {
            state.regionId = action.payload;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(fetchRegions.pending, (state) => {
                state.error = undefined;
                state.isLoading = true;
            })
            .addCase(fetchRegions.fulfilled, (state, action: PayloadAction<Region[]>) => {
                state.isLoading = false;
                state.data = action.payload;
            })
            .addCase(fetchRegions.rejected, (state, action) => {
                state.isLoading = false;
                state.error = action.payload as string;
            });
    },
});

// Action creators are generated for each case reducer function
export const { actions: regionsSliceActions } = regionsSlice;
export const { reducer: regionsSliceReducer } = regionsSlice;
