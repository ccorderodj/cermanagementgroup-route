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

export async function fetchVehicles(): Promise<Vehicle[]> {
    const response = await $api.get('/vehicles');
    return parseApi(listSchema, response.data, 'fetchVehicles');
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
