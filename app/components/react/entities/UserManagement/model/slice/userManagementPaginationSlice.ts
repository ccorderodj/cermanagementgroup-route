import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { fetchUserManagementPagination } from '../services';
import {
    UserManagementEntity,
    UserManagementPaginationResult,
    UserManagementPaginationSchema,
} from '../types';

const initialState: UserManagementPaginationSchema = {
    isLoading: false,
    error: undefined,
    data: {
        results: [],
        next: '',
        previous: '',
        count: 0,
        page_size: 10,
        index_page: 0,
    },
};

export const userManagementPaginationSlice = createSlice({
    name: 'userManagementPaginationSlice',
    initialState,
    reducers: {
        add: (state, action: PayloadAction<{ index: number; data: UserManagementEntity }>) => {
            state.data.results = [{ ...action.payload.data }, ...state.data.results];
            state.data.count += 1;
        },
        update: (state, action: PayloadAction<{ index: number; data: UserManagementEntity }>) => {
            const { index, data } = action.payload;
            state.data.results[index] = {
                ...state.data.results[index],
                ...data,
            };
        },
        setPageSize: (state, action: PayloadAction<number>) => {
            state.data.page_size = action.payload;
        },
        setIndexPage: (state, action: PayloadAction<number>) => {
            state.data.index_page = action.payload;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(fetchUserManagementPagination.pending, (state) => {
                state.error = undefined;
                state.isLoading = true;
            })
            .addCase(fetchUserManagementPagination.fulfilled, (state, action: PayloadAction<UserManagementPaginationResult>) => {
                state.isLoading = false;
                state.data.results = action.payload.results;
                state.data.count = action.payload.count;
                state.data.next = action.payload.next;
                state.data.previous = action.payload.previous;
            })
            .addCase(fetchUserManagementPagination.rejected, (state, action) => {
                state.isLoading = false;
                state.error = action.payload as string;
            });
    },
});

export const { actions: userManagementPaginationSliceActions } = userManagementPaginationSlice;
export const { reducer: userManagementPaginationSliceReducer } = userManagementPaginationSlice;
