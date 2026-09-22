import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { fetchRolePermissionChangeRequestsPagination } from '../services';
import {
    RolePermissionChangeRequestEntity,
    RolePermissionChangeRequestPaginationResult,
    RolePermissionChangeRequestsPaginationSchema,
} from '../types';

const initialState: RolePermissionChangeRequestsPaginationSchema = {
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

export const rolePermissionChangeRequestsPaginationSlice = createSlice({
    name: 'rolePermissionChangeRequestsPaginationSlice',
    initialState,
    reducers: {
        add: (state, action: PayloadAction<{ index: number; data: RolePermissionChangeRequestEntity }>) => {
            state.data.results = [{ ...action.payload.data }, ...state.data.results];
            state.data.count += 1;
        },
        update: (state, action: PayloadAction<{ index: number; data: RolePermissionChangeRequestEntity }>) => {
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
            .addCase(fetchRolePermissionChangeRequestsPagination.pending, (state) => {
                state.error = undefined;
                state.isLoading = true;
            })
            .addCase(
                fetchRolePermissionChangeRequestsPagination.fulfilled,
                (state, action: PayloadAction<RolePermissionChangeRequestPaginationResult>) => {
                    state.isLoading = false;
                    state.data.results = action.payload.results;
                    state.data.count = action.payload.count;
                    state.data.next = action.payload.next;
                    state.data.previous = action.payload.previous;
                },
            )
            .addCase(fetchRolePermissionChangeRequestsPagination.rejected, (state, action) => {
                state.isLoading = false;
                state.error = action.payload as string;
            });
    },
});

export const { actions: rolePermissionChangeRequestsPaginationSliceActions } = rolePermissionChangeRequestsPaginationSlice;
export const { reducer: rolePermissionChangeRequestsPaginationSliceReducer } = rolePermissionChangeRequestsPaginationSlice;
