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
 * Qué se guarda en el aparato y qué no
 * -------------------------------------
 * **La foto sí** (RTE10-A01 FR-06). Se escribe en IndexedDB antes de intentar
 * subirla y se retira cuando el servidor confirma que la tiene, de forma que
 * una página recreada por falta de memoria o un túnel sin cobertura no obliguen
 * al supervisor a volver al vehículo a repetirla. El carril vive en
 * `shared/lib/offlineQueue`, en la misma base que los otros dos.
 *
 * Hasta RTE04 esto no se hacía, y el motivo escrito entonces era bueno: encolar
 * binarios de varios megabytes trae cuota del navegador, expulsión silenciosa y
 * reintentos parciales. Lo que cambió es que el coste del otro lado se midió en
 * campo —el supervisor perdía la foto— y FR-06 lo pide de forma acotada: sólo
 * la foto, sólo hasta que el servidor la confirme.
 *
 * **La confirmación de la lectura no**, y por la razón de RTE04, que sigue
 * valiendo entera: lo que el supervisor necesita saber es si **ya puede salir**.
 * Una confirmación encolada le diría que sí mientras el servidor todavía puede
 * rechazarla, y volvería a arrancar el coche con la evidencia sin resolver.
 * Aquí se prefiere un error honesto de conexión.
 *
 * La diferencia entre las dos es que la foto **no afirma nada del dominio**: es
 * el archivo que la evidencia necesitará cuando llegue. La confirmación sí
 * afirma, y por eso no se puede prometer en nombre del servidor.
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
