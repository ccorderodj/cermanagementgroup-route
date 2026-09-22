import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { fetchRolesPagination } from '../services';
import {
    RoleEntity,
    RolePaginationResult,
    RolesPaginationSchema,
} from '../types';

const initialState: RolesPaginationSchema = {
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

export const rolesPaginationSlice = createSlice({
    name: 'rolesPaginationSlice',
    initialState,
    reducers: {
        add: (state, action: PayloadAction<{ index: number; data: RoleEntity }>) => {
            state.data.results = [{ ...action.payload.data }, ...state.data.results];
            state.data.count += 1;
        },
        update: (state, action: PayloadAction<{ index: number; data: RoleEntity }>) => {
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
            .addCase(fetchRolesPagination.pending, (state) => {
                state.error = undefined;
                state.isLoading = true;
            })
            .addCase(fetchRolesPagination.fulfilled, (state, action: PayloadAction<RolePaginationResult>) => {
                state.isLoading = false;
                state.data.results = action.payload.results;
                state.data.count = action.payload.count;
                state.data.next = action.payload.next;
                state.data.previous = action.payload.previous;
            })
            .addCase(fetchRolesPagination.rejected, (state, action) => {
                state.isLoading = false;
                state.error = action.payload as string;
            });
    },
});

export const { actions: rolesPaginationSliceActions } = rolesPaginationSlice;
export const { reducer: rolesPaginationSliceReducer } = rolesPaginationSlice;
