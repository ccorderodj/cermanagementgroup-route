import { z } from 'zod';
import { $api, parseApi } from '@/shared/api';
import { enqueueAction, type PendingAction } from '@/shared/lib/offlineQueue';
import { captureTimeEvidence } from '@/shared/lib/utils/utils';
import {
    tripPurposeChangeSchema,
    tripSchema,
    type TripPlanInput,
    type TripPurposeChange,
} from '../types';

/**
 * Acciones del viaje.
 *
 * Las que **mutan** pasan por la cola durable de RTE03 —la misma, no una
 * segunda—: se escriben en IndexedDB antes de darse por aceptadas y se
 * reenvían al recuperar conexión. Con cobertura el envío ocurre en el mismo
 * instante y la diferencia con una llamada directa es imperceptible.
 *
 * Las de **lectura** van directas: no hay nada que encolar en una consulta, y
 * sin red simplemente no hay respuesta que dar.
 *
 * El identificador de cada acción encolada viaja como `Idempotency-Key`, así
 * que reenviarla no repite la escritura ni duplica el viaje.
 */

export async function queuePlanTrip(input: TripPlanInput): Promise<PendingAction> {
    return enqueueAction('trip.plan', '/trips', {
        ...input,
        ...captureTimeEvidence(),
    });
}

export async function queueStartTrip(tripId: number): Promise<PendingAction> {
    return enqueueAction('trip.start', `/trips/${tripId}/start`, {
        ...captureTimeEvidence(),
    });
}

export async function queueArrive(tripId: number): Promise<PendingAction> {
    return enqueueAction('trip.arrive', `/trips/${tripId}/arrive`, {
        ...captureTimeEvidence(),
    });
}

/**
 * Cambiar el plan no se encola.
 *
 * El servidor rechaza el cambio si el viaje ya no está en tránsito, y esa
 * respuesta hay que verla en el momento: encolarlo dejaría al supervisor
 * creyendo que cambió de destino para descubrir al reconectar que no. Es una
 * limitación honesta del alcance offline de RTE04, no un olvido.
 */
export async function changeTripPlan(
    tripId: number,
    input: TripPlanInput,
): Promise<void> {
    await $api.post(`/trips/${tripId}/change-plan`, { ...input });
}

export async function fetchPlanChanges(
    tripId: number,
): Promise<TripPurposeChange[]> {
    const response = await $api.get(`/trips/${tripId}/plan-changes`);
    return parseApi(
        z.array(tripPurposeChangeSchema),
        response.data,
        'fetchPlanChanges',
    );
}

/** Valida la respuesta de un viaje suelto, para quien la necesite. */
export const parseTrip = (data: unknown) => parseApi(tripSchema, data, 'parseTrip');
