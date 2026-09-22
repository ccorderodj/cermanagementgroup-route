import { z } from 'zod';

/**
 * Grados de combustible del modelo certificado en RTE01.
 *
 * Es un enum **del producto**, no un dato del tenant: por eso está aquí y no
 * en `standard_value`. La base lo respalda con un `CHECK`, así que esta lista y
 * la de PostgreSQL tienen que decir lo mismo.
 */
export const FUEL_GRADES = ['regular', 'midgrade', 'premium', 'diesel'] as const;

export const fuelGradeSchema = z.enum(FUEL_GRADES);
export type FuelGrade = z.infer<typeof fuelGradeSchema>;

export const FUEL_GRADE_LABELS: Record<FuelGrade, string> = {
    regular: 'Regular',
    midgrade: 'Midgrade',
    premium: 'Premium',
    diesel: 'Diesel',
};

/**
 * Un vehículo de la compañía.
 *
 * `operational_mpg` llega como cadena: es `Numeric` en la base y el JSON lo
 * serializa así para no perder precisión por el camino. Se deja como cadena a
 * propósito —se muestra, no se opera con ella en el cliente— y el cálculo de
 * combustible, cuando llegue, es del servidor.
 */
export const vehicleSchema = z.object({
    id: z.number(),
    make: z.string(),
    model: z.string(),
    year: z.number(),
    unit: z.string(),
    fuel_grade: z.string(),
    operational_mpg: z.union([z.string(), z.number()]).transform(String),
    is_active: z.boolean(),
    version: z.number(),
    created_at: z.string(),
    updated_at: z.string(),
});

export type Vehicle = z.infer<typeof vehicleSchema>;

/** Alta de vehículo. */
export interface VehicleCreateInput {
    make: string;
    model: string;
    year: number;
    unit: string;
    fuel_grade: FuelGrade;
    operational_mpg: string;
}

/**
 * Edición. `version` viaja siempre que se conozca: es lo que hace que dos
 * administradores editando la misma ficha reciban un 409 en vez de pisarse.
 */
export interface VehicleUpdateInput extends Partial<VehicleCreateInput> {
    is_active?: boolean;
    version?: number;
}
