import { createSlice } from '@reduxjs/toolkit';

import { login, logout } from '../services';
import { LoginSchema } from '../types';

/**
 * Estado de la sesion.
 *
 * Guarda si hay sesion y el correo con el que se entro. **No guarda la
 * contrasena** —el slice anterior la dejaba en el store, y por tanto en las
 * DevTools de Redux— ni el token: el token vive en una cookie HttpOnly que el
 * JavaScript no puede leer, que es justo el motivo de marcarla asi.
 */
const initialState: LoginSchema = {
    isLoading: false,
    error: undefined,
    email: '',
    isAuthenticated: false,
};

export const loginSlice = createSlice({
    name: 'loginSlice',
    initialState,
    reducers: {},
    extraReducers: (builder) => {
        builder
            .addCase(login.pending, (state) => {
                state.error = undefined;
                state.isLoading = true;
            })
            .addCase(login.fulfilled, (state, action) => {
                state.isLoading = false;
                state.isAuthenticated = true;
                state.email = action.meta.arg.email;
            })
            .addCase(login.rejected, (state, action) => {
                state.isLoading = false;
                state.isAuthenticated = false;
                state.error = action.payload as string;
            })
            .addCase(logout.fulfilled, (state) => {
                state.isAuthenticated = false;
                state.email = '';
            });
    },
});

export const { actions: loginSliceActions } = loginSlice;
export const { reducer: loginSliceReducer } = loginSlice;
