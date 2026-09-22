import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import {
    fetchCompaniesPagination,
} from '../services';
import { CompaniesPaginationResult, CompaniesPaginationSchema } from '../types';

const initialState: CompaniesPaginationSchema = {
    isLoading: false,
    error: undefined,
    data: {
        results: [],
        next: '',
        previous: '',
        count: 0, // totalCount
        page_size: 10, // pageSize
        index_page: 0,
    },
};

export const companiesPaginationSlice = createSlice({
    name: 'companiesPaginationSlice',
    initialState,
    reducers: {
        setPageSize: (state, action: PayloadAction<number>) => {
            state.data.page_size = action.payload;
        },
        setIndexPage: (state, action: PayloadAction<number>) => {
            state.data.index_page = action.payload;
        },
        // updateEmployee: (state, action: PayloadAction<{ index: number, updatedRow: Employee }>) => {
        //     const { index, updatedRow } = action.payload;
        //     // Replace the entire row at the specified index with the new row data
        //     state.data.results[index] = {
        //         ...state.data.results[index], // Keep the current row properties
        //         ...updatedRow, // Overwrite with updated row properties
        //     };
        // },
        // addSubClientEmployee: (state, action: PayloadAction<{ index: number, employee: Employee }>) => {
        //     const { index, employee } = action.payload;

        //     state.data.results = [
        //         { ...employee },
        //         ...state.data.results,
        //     ];
        // },
    },
    extraReducers: (builder) => {
        builder
            .addCase(fetchCompaniesPagination.pending, (state) => {
                state.error = undefined;
                state.isLoading = true;
            })
            .addCase(fetchCompaniesPagination.fulfilled, (state, action: PayloadAction<CompaniesPaginationResult>) => {
                state.isLoading = false;
                state.data.results = action.payload.results;
                state.data.count = action.payload.count;
                state.data.next = action.payload.next;
                state.data.previous = action.payload.previous;
            })
            .addCase(fetchCompaniesPagination.rejected, (state, action) => {
                state.isLoading = false;
                state.error = action.payload as string;
            });
    },
});

// Action creators are generated for each case reducer function
export const { actions: companiesPaginationSliceActions } = companiesPaginationSlice;
export const { reducer: companiesPaginationSliceReducer } = companiesPaginationSlice;
