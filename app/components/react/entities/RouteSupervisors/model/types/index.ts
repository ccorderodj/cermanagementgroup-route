import { z } from 'zod';
import { vehicleSchema } from '@/entities/RouteVehicles';

/**
 * Supervisor de Route.
 *
 * `first_name`, `last_name` y `email` vienen resueltos desde `user` por el
 * servidor: **no** están duplicados en `supervisor_profile`. El perfil es una
 * extensión de dominio, no una segunda ficha de persona.
 *
 * `current_vehicle` se deriva de la asignación vigente. `null` es un estado
 * normal —un supervisor recién dado de alta—, no un error.
 */
export const supervisorProfileSchema = z.object({
    id: z.number(),
    user_id: z.number(),
    first_name: z.string(),
    last_name: z.string(),
    email: z.string(),
    is_active: z.boolean(),
    version: z.number(),
    created_at: z.string(),
    updated_at: z.string(),
    current_vehicle: vehicleSchema.nullable().optional(),
});

export type SupervisorProfile = z.infer<typeof supervisorProfileSchema>;

/** Una asignación del historial. `effective_to: null` significa vigente. */
export const vehicleAssignmentSchema = z.object({
    id: z.number(),
    supervisor_profile_id: z.number(),
    vehicle_id: z.number(),
    effective_from: z.string(),
    effective_to: z.string().nullable().optional(),
    created_at: z.string(),
    updated_at: z.string(),
    vehicle_unit: z.string().nullable().optional(),
    vehicle_make: z.string().nullable().optional(),
    vehicle_model: z.string().nullable().optional(),
    vehicle_year: z.number().nullable().optional(),
});

export type VehicleAssignment = z.infer<typeof vehicleAssignmentSchema>;
