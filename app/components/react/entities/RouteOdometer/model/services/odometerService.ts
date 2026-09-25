import { z } from 'zod';
import { $api, parseApi } from '@/shared/api';
import {
    odometerEvidenceSchema,
    odometerExceptionQueueRowSchema,
    odometerExceptionSchema,
    odometerPhotoResultSchema,
    odometerSessionStateSchema,
    type OdometerEnd,
    type OdometerEvidence,
    type OdometerException,
    type OdometerExceptionQueueRow,
    type OdometerExceptionReason,
    type OdometerPhotoResult,
    type OdometerSessionState,
} from '../types';

/**
 * Servicio de la evidencia de odómetro.
 *
 * Por qué **nada de esto se encola**
 * -----------------------------------
 * La cola durable de RTE03 guarda cuerpos JSON en IndexedDB, y aquí el hecho
 * central es una fotografía: encolar binarios de varios megabytes es otro
 * problema —cuota del navegador, expulsión silenciosa, reintentos parciales— y
 * RTE04 declara explícitamente que no lo resuelve.
 *
 * Y aunque se resolviera, encolar sería la decisión equivocada para esta
 * pantalla: lo que el supervisor necesita saber es si **ya puede salir**. Una
 * confirmación encolada le diría que sí mientras el servidor todavía puede
 * rechazarla, y volvería a arrancar el coche con la evidencia sin resolver.
 * Aquí se prefiere un error honesto de conexión.
 */

export async function fetchSessionOdometer(
    sessionId: number,
): Promise<OdometerSessionState> {
    const response = await $api.get(`/odometer/sessions/${sessionId}`);
    return parseApi(
        odometerSessionStateSchema,
        response.data,
        'fetchSessionOdometer',
    );
}

/**
 * Sube la foto del cuentakilómetros e intenta una sugerencia.
 *
 * `ocr_suggestion` puede venir vacía y no es un fallo: la pantalla ofrece el
 * teclado en vez de un borrador, y la evidencia sigue siendo fotográfica.
 */
export async function uploadOdometerPhoto(
    sessionId: number,
    end: OdometerEnd,
    photo: File,
): Promise<OdometerPhotoResult> {
    const formulario = new FormData();
    formulario.append('photo', photo);
    const response = await $api.post(
        `/odometer/sessions/${sessionId}/${end}/photo`,
        formulario,
    );
    return parseApi(
        odometerPhotoResultSchema,
        response.data,
        'uploadOdometerPhoto',
    );
}

/** La lectura que confirma la persona. Aquí está la autoridad del dato. */
export async function confirmOdometerReading(
    sessionId: number,
    end: OdometerEnd,
    reading: string,
): Promise<OdometerEvidence> {
    const response = await $api.post(
        `/odometer/sessions/${sessionId}/${end}/confirm`,
        { reading },
    );
    return parseApi(
        odometerEvidenceSchema,
        response.data,
        'confirmOdometerReading',
    );
}

/** Pide permiso para teclear sin foto. No lo concede: lo pide. */
export async function requestOdometerException(
    sessionId: number,
    end: OdometerEnd,
    reason: OdometerExceptionReason,
    reasonNote?: string | null,
): Promise<OdometerException> {
    const response = await $api.post(
        `/odometer/sessions/${sessionId}/${end}/exception`,
        { reason, reason_note: reasonNote?.trim() || null },
    );
    return parseApi(
        odometerExceptionSchema,
        response.data,
        'requestOdometerException',
    );
}

// ── Administración ──────────────────────────────────────────────────────────

type ColaDeExcepciones = Promise<OdometerExceptionQueueRow[]>;

export async function fetchPendingOdometerExceptions(): ColaDeExcepciones {
    const response = await $api.get('/odometer/exceptions/pending');
    return parseApi(
        z.array(odometerExceptionQueueRowSchema),
        response.data,
        'fetchPendingOdometerExceptions',
    );
}

/**
 * Aprobar autoriza **una** entrada manual, para esa jornada y ese extremo.
 * No escribe ninguna lectura: eso sigue siendo del supervisor.
 */
export async function approveOdometerException(
    requestId: number,
): Promise<OdometerException> {
    const response = await $api.post(`/odometer/exceptions/${requestId}/approve`);
    return parseApi(
        odometerExceptionSchema,
        response.data,
        'approveOdometerException',
    );
}

export async function rejectOdometerException(
    requestId: number,
): Promise<OdometerException> {
    const response = await $api.post(`/odometer/exceptions/${requestId}/reject`);
    return parseApi(
        odometerExceptionSchema,
        response.data,
        'rejectOdometerException',
    );
}

/**
 * La URL de la foto de una evidencia.
 *
 * No es pública ni permanente: el endpoint vuelve a comprobar tenant y
 * propiedad en cada lectura, así que esta cadena por sí sola no abre nada.
 */
export const odometerPhotoUrl = (evidenceId: number): string => (
    `/api/odometer/evidence/${evidenceId}/photo`
);
