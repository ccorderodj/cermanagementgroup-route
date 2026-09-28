import { AxiosError } from 'axios';
import { createAsyncThunk } from '@reduxjs/toolkit';
import { z } from 'zod';
import { ThunkConfig } from '@/app/providers/StoreProvider';
import { parseApi } from '@/shared/api';
import { handleAsyncError } from '@/shared/lib/utils/utils';

/**
 * Los roles que **quien está autenticado** puede conceder en esta compañía.
 *
 * Por qué esto y no `fetchRoles()`
 * ---------------------------------
 * El formulario pedía el catálogo de roles del tenant y ofrecía los seis. Dentro
 * de CER Route eso era ofrecer `owner` y `admin` como si fueran personas de este
 * producto, y el servidor los aceptaba: la escalada que midió el diagnóstico
 * A01. Ahora el servidor sólo acepta los dos roles de Route, y este endpoint
 * devuelve exactamente lo que aceptaría.
 *
 * Sirve a las dos audiencias con una sola llamada: quien administra desde el
 * núcleo sigue recibiendo el catálogo completo. Y no necesita `roles.read` —le
 * basta `users.read`—, que es lo que permitió retirar esa capacidad del
 * Administrador de Route sin romperle el formulario.
 *
 * Esto **no** es el control. Ocultar una opción mejora la experiencia; quien
 * mande otro rol por API recibe 403 igual.
 */

export const assignableRoleSchema = z.object({
    id: z.number(),
    /** Código técnico interno. No se muestra nunca. */
    code: z.string(),
    /** Cómo se llama en pantalla: "Administrador", "Supervisor". */
    label: z.string(),
});

export type AssignableRole = z.infer<typeof assignableRoleSchema>;

export const fetchAssignableRoles = createAsyncThunk<
    AssignableRole[],
    void,
    ThunkConfig<string>
>(
    'userManagement/fetchAssignableRoles',
    async (_, thunkApi) => {
        const { extra, rejectWithValue } = thunkApi;
        try {
            const response = await extra.api.get('/users/assignable-roles');
            return parseApi(
                z.array(assignableRoleSchema),
                response.data,
                'fetchAssignableRoles',
            );
        } catch (error) {
            return handleAsyncError(error as AxiosError, rejectWithValue);
        }
    },
);
