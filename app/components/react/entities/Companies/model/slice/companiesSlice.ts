import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import {
    fetchCompanies,
} from '../services';
import { CompaniesSchema, Company } from '../types';

const initialState: CompaniesSchema = {
    isLoading: false,
    error: undefined,
    data: [],
};

export const companiesSlice = createSlice({
    name: 'companiesSlice',
    initialState,
    reducers: {
        setCompanyId: (state, action: PayloadAction<number>) => {
            state.companyId = action.payload;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(fetchCompanies.pending, (state) => {
                state.error = undefined;
                state.isLoading = true;
            })
            .addCase(fetchCompanies.fulfilled, (state, action: PayloadAction<Company[]>) => {
                state.isLoading = false;
                state.data = action.payload;
            })
            .addCase(fetchCompanies.rejected, (state, action) => {
                state.isLoading = false;
                state.error = action.payload as string;
            });
    },
});

// Action creators are generated for each case reducer function
export const { actions: companiesSliceActions } = companiesSlice;
export const { reducer: companiesSliceReducer } = companiesSlice;
