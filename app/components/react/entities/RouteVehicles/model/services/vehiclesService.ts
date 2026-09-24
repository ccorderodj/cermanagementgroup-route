import { z } from 'zod';
import { $api, parseApi } from '@/shared/api';
import {
    vehicleSchema,
    type Vehicle,
    type VehicleCreateInput,
    type VehicleUpdateInput,
} from '../types';

/**
 * Llamadas a la API de vehículos.
 *
 * Todas validan la respuesta con Zod antes de devolverla. `api.get<T>()` no
 * comprueba nada —el genérico es una promesa del programador, no del
 * servidor—, así que un contrato roto se detecta aquí y no tres pantallas más
 * adelante con un `undefined` inexplicable.
 */

const listSchema = z.array(vehicleSchema);

/**
 * Vehículos **activos**: es el selector operativo de asignación.
 *
 * No sirve para administrar. Un vehículo desactivado no sale de aquí, que es
 * justo lo que se quiere al elegir vehículo para alguien, y justo lo que no se
 * quiere al gestionarlos. Para eso está `fetchVehiclesForAdmin`.
 */
export async function fetchVehicles(): Promise<Vehicle[]> {
    const response = await $api.get('/vehicles');
    return parseApi(listSchema, response.data, 'fetchVehicles');
}

/**
 * Vehículos para la pantalla de administración: activos y, si se pide,
 * también los inactivos.
 *
 * Antes la pantalla usaba `fetchVehicles`, que sólo devuelve activos: un
 * vehículo desactivado desaparecía de la tabla y no había forma de reactivarlo
 * desde el producto, aunque el badge y el botón existieran en el código.
 *
 * Los borrados no aparecen en ningún caso: el servidor no los sirve.
 */
export async function fetchVehiclesForAdmin(
    includeInactive = false,
): Promise<Vehicle[]> {
    const response = await $api.get('/vehicles/pagination', {
        params: {
            page: 1,
            page_size: 100,
            ...(includeInactive ? {} : { is_active: true }),
        },
    });
    return parseApi(
        z.object({ results: listSchema }),
        response.data,
        'fetchVehiclesForAdmin',
    ).results;
}

export async function createVehicle(input: VehicleCreateInput): Promise<Vehicle> {
    const response = await $api.post('/vehicles', input);
    return parseApi(vehicleSchema, response.data, 'createVehicle');
}

export async function updateVehicle(
    vehicleId: number,
    input: VehicleUpdateInput,
): Promise<Vehicle> {
    const response = await $api.put(`/vehicles/${vehicleId}`, input);
    return parseApi(vehicleSchema, response.data, 'updateVehicle');
}

export async function setVehicleActive(
    vehicleId: number,
    isActive: boolean,
    version?: number,
): Promise<Vehicle> {
    const accion = isActive ? 'activate' : 'deactivate';
    const response = await $api.post(`/vehicles/${vehicleId}/${accion}`, { version });
    return parseApi(vehicleSchema, response.data, 'setVehicleActive');
}

/**
 * Saca el vehículo de la administración. Distinto de `setVehicleActive(false)`,
 * que sólo lo retira del uso dejándolo visible y reactivable.
 *
 * Responde 409 si tiene una asignación vigente: el motivo viene del servidor en
 * lenguaje normal, listo para enseñarlo.
 */
export async function deleteVehicle(
    vehicleId: number,
    version?: number,
): Promise<void> {
    await $api.delete(`/vehicles/${vehicleId}`, {
        params: version === undefined ? undefined : { version },
    });
}
