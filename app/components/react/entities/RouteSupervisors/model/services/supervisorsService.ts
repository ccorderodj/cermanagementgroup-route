import { z } from 'zod';
import { $api, parseApi } from '@/shared/api';
import {
    supervisorCandidateSchema,
    supervisorProfileSchema,
    vehicleAssignmentSchema,
    type SupervisorCandidate,
    type SupervisorProfile,
    type VehicleAssignment,
} from '../types';

/** Llamadas a la API de supervisores y asignaciones, validadas con Zod. */

export async function fetchSupervisors(): Promise<SupervisorProfile[]> {
    const response = await $api.get('/supervisors');
    return parseApi(z.array(supervisorProfileSchema), response.data, 'fetchSupervisors');
}

/**
 * El perfil de quien llama. Devuelve `null` si no es supervisor en esta
 * compañía, que es lo que verá un administrador abriendo la pantalla.
 */
export async function fetchMySupervisorProfile(): Promise<SupervisorProfile | null> {
    const response = await $api.get('/supervisors/me');
    if (response.data === null || response.data === undefined || response.data === '') {
        return null;
    }
    return parseApi(supervisorProfileSchema, response.data, 'fetchMySupervisorProfile');
}

export async function createSupervisorProfile(userId: number): Promise<SupervisorProfile> {
    const response = await $api.post('/supervisors', { user_id: userId });
    return parseApi(supervisorProfileSchema, response.data, 'createSupervisorProfile');
}

export async function fetchAssignmentHistory(
    supervisorProfileId: number,
): Promise<VehicleAssignment[]> {
    const response = await $api.get(`/supervisors/${supervisorProfileId}/assignments`);
    return parseApi(
        z.array(vehicleAssignmentSchema),
        response.data,
        'fetchAssignmentHistory',
    );
}

export async function assignVehicle(
    supervisorProfileId: number,
    vehicleId: number,
): Promise<VehicleAssignment> {
    const response = await $api.post(
        `/supervisors/${supervisorProfileId}/assignments`,
        { vehicle_id: vehicleId },
    );
    return parseApi(vehicleAssignmentSchema, response.data, 'assignVehicle');
}

export async function endAssignment(assignmentId: number): Promise<VehicleAssignment> {
    const response = await $api.post(`/supervisors/assignments/${assignmentId}/end`, {});
    return parseApi(vehicleAssignmentSchema, response.data, 'endAssignment');
}

/** Usuarios del tenant con su condición de supervisor y su vehículo vigente. */
export async function fetchSupervisorCandidates(): Promise<SupervisorCandidate[]> {
    const response = await $api.get('/supervisors/candidates');
    return parseApi(
        z.array(supervisorCandidateSchema),
        response.data,
        'fetchSupervisorCandidates',
    );
}

/** Designa supervisor de Route a un usuario que ya pertenece a la compañía. */
export async function designateSupervisor(userId: number): Promise<SupervisorProfile> {
    const response = await $api.post('/supervisors', { user_id: userId });
    return parseApi(supervisorProfileSchema, response.data, 'designateSupervisor');
}

/** Retira o restaura la designación. No la borra: la historia la referencia. */
export async function setSupervisorDesignation(
    supervisorProfileId: number,
    isActive: boolean,
    version?: number,
): Promise<SupervisorProfile> {
    const response = await $api.put(`/supervisors/${supervisorProfileId}`, {
        is_active: isActive,
        version,
    });
    return parseApi(supervisorProfileSchema, response.data, 'setSupervisorDesignation');
}

/**
 * Fija o quita el override de zona horaria (T-1/T-2). `null` lo quita y la
 * zona vuelve a salir del dispositivo en cada jornada. Es una excepción, no
 * una configuración obligatoria: sin él, todo funciona solo.
 */
/**
 * Fija o quita el estado operativo (RTE09 D-1). Decide qué precio de
 * combustible aplica a las jornadas que empiecen después; las anteriores
 * conservan el suyo. `null` lo quita.
 */
export async function setSupervisorOperationalState(
    supervisorProfileId: number,
    stateCode: string | null,
    version?: number,
): Promise<SupervisorProfile> {
    const response = await $api.put(`/supervisors/${supervisorProfileId}/operational-state`, {
        operational_state: stateCode,
        version,
    });
    return parseApi(supervisorProfileSchema, response.data, 'setSupervisorOperationalState');
}

/** Los estados de EE. UU. del catálogo, para elegir el operativo. */
export async function fetchStateCatalog(): Promise<{ code: string; name: string }[]> {
    const response = await $api.get('/regions/catalog');
    return parseApi(
        z.array(z.object({ code: z.string(), name: z.string() }).passthrough()),
        response.data,
        'fetchStateCatalog',
    );
}

export async function setSupervisorTimeZone(
    supervisorProfileId: number,
    timeZone: string | null,
    version?: number,
): Promise<SupervisorProfile> {
    const response = await $api.put(`/supervisors/${supervisorProfileId}/time-zone`, {
        operational_time_zone: timeZone,
        version,
    });
    return parseApi(supervisorProfileSchema, response.data, 'setSupervisorTimeZone');
}

/**
 * Saca la designación de Route de la administración. **No borra al usuario**:
 * la identidad es del núcleo y la persona sigue en el tenant.
 *
 * Responde 409 si el supervisor todavía tiene un vehículo asignado.
 */
export async function deleteSupervisorProfile(
    supervisorProfileId: number,
    version?: number,
): Promise<void> {
    await $api.delete(`/supervisors/${supervisorProfileId}`, {
        params: version === undefined ? undefined : { version },
    });
}
