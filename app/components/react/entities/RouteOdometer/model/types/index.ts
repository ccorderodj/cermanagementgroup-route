import { z } from 'zod';

/**
 * Evidencia de odómetro (RTE04). **No es millaje de ruta.**
 *
 * Son dos hechos distintos y el tipo lo mantiene visible: esto es la lectura
 * del cuentakilómetros de una jornada, evidencia de referencia. El millaje
 * oficial de la ruta lo calcula otro dominio, y nada de aquí lo alimenta.
 */

export const ODOMETER_ENDS = ['start', 'end'] as const;
export const odometerEndSchema = z.enum(ODOMETER_ENDS);
export type OdometerEnd = z.infer<typeof odometerEndSchema>;

/**
 * Los seis estados de un extremo.
 *
 * `not_required` no es un cero ni un "vacío": dice que esta jornada no llevaba
 * vehículo aplicable, así que pedir una foto sería inventar una necesidad.
 * `photo_confirmed` y `manual_exception_confirmed` resuelven los dos, pero
 * siguen siendo **distinguibles para siempre**, que es justo el punto.
 */
export const odometerStatusSchema = z.enum([
    'pending',
    'exception_requested',
    'exception_approved',
    'photo_confirmed',
    'manual_exception_confirmed',
    'not_required',
]);
export type OdometerStatus = z.infer<typeof odometerStatusSchema>;

export const odometerMethodSchema = z.enum(['photo', 'manual_no_photo']);
export type OdometerMethod = z.infer<typeof odometerMethodSchema>;

/** Los estados en los que ya no hace falta nada del supervisor. */
export const ODOMETER_RESOLVED: readonly OdometerStatus[] = [
    'photo_confirmed',
    'manual_exception_confirmed',
    'not_required',
];

export const isOdometerResolved = (status: OdometerStatus): boolean => (
    ODOMETER_RESOLVED.includes(status)
);

/**
 * Decimales por cable.
 *
 * El servidor serializa `Decimal` como cadena para no perder precisión al
 * pasar por el doble de coma flotante de JavaScript. Se acepta también número
 * por si un intermediario lo normaliza, y se convierte una sola vez aquí.
 */
const decimalSchema = z.union([z.string(), z.number()]).nullable().optional();

export const odometerEvidenceSchema = z.object({
    id: z.number(),
    work_session_id: z.number(),
    vehicle_id: z.number().nullable().optional(),
    evidence_type: odometerEndSchema,
    status: odometerStatusSchema,
    evidence_method: odometerMethodSchema.nullable().optional(),

    // La lectura que confirmó la persona y la que sugirió la máquina viajan
    // juntas y separadas: son hechos distintos y el OCR nunca es autoridad.
    confirmed_reading: decimalSchema,
    ocr_detected_reading: decimalSchema,

    captured_at: z.string().nullable().optional(),
    confirmed_at: z.string().nullable().optional(),
    confirmed_by: z.number().nullable().optional(),
    version: z.number(),
});

export type OdometerEvidence = z.infer<typeof odometerEvidenceSchema>;

export const odometerSessionStateSchema = z.object({
    start: odometerEvidenceSchema.nullable().optional(),
    end: odometerEvidenceSchema.nullable().optional(),
    // `null` mientras falte una de las dos lecturas. **No es cero**: significa
    // que todavía no se puede afirmar una distancia.
    odometer_distance: decimalSchema,
});

export type OdometerSessionState = z.infer<typeof odometerSessionStateSchema>;

export const odometerPhotoResultSchema = z.object({
    evidence: odometerEvidenceSchema,
    // Puede venir vacía, y es normal: el OCR es asistivo. Sin sugerencia el
    // supervisor teclea lo que ve en la foto y sigue siendo evidencia
    // fotográfica, sin aprobación de nadie.
    ocr_suggestion: decimalSchema,
});

export type OdometerPhotoResult = z.infer<typeof odometerPhotoResultSchema>;

/**
 * Los motivos para pedir teclear sin foto. Lista cerrada a propósito.
 *
 * Un campo libre convertiría la excepción en un permiso permanente
 * disfrazado que nadie podría revisar por agregado.
 */
export const ODOMETER_EXCEPTION_REASONS = [
    'camera_unavailable',
    'no_usable_photo',
    'vehicle_inaccessible',
    'other',
] as const;

export const odometerExceptionReasonSchema = z.enum(ODOMETER_EXCEPTION_REASONS);
export type OdometerExceptionReason = z.infer<typeof odometerExceptionReasonSchema>;

export const ODOMETER_REASON_LABELS: Record<OdometerExceptionReason, string> = {
    camera_unavailable: 'The camera is not working',
    no_usable_photo: 'The photo is not readable',
    vehicle_inaccessible: 'I cannot reach the vehicle',
    other: 'Something else',
};

export const odometerExceptionStatusSchema = z.enum([
    'requested',
    'approved',
    'rejected',
    'consumed',
]);
export type OdometerExceptionStatus = z.infer<typeof odometerExceptionStatusSchema>;

export const odometerExceptionSchema = z.object({
    id: z.number(),
    work_session_id: z.number(),
    vehicle_id: z.number().nullable().optional(),
    evidence_type: odometerEndSchema,
    status: odometerExceptionStatusSchema,
    reason: odometerExceptionReasonSchema,
    reason_note: z.string().nullable().optional(),
    requested_by: z.number(),
    requested_at: z.string(),
    decided_by: z.number().nullable().optional(),
    decided_at: z.string().nullable().optional(),
    consumed_at: z.string().nullable().optional(),
    version: z.number(),
});

export type OdometerException = z.infer<typeof odometerExceptionSchema>;

/**
 * Una fila de la cola del administrador.
 *
 * Trae el nombre de quien la pidió y la unidad del vehículo porque quien decide
 * necesita saber **sobre quién** decide: una pantalla de identificadores
 * numéricos empuja a aprobar por inercia, que es justo lo contrario de lo que
 * esta revisión existe para conseguir.
 */
export const odometerExceptionQueueRowSchema = odometerExceptionSchema.extend({
    requested_by_name: z.string(),
    vehicle_unit: z.string().nullable().optional(),
    // La zona de la jornada de la solicitud (T-1/T-2). Opcionales para leer
    // igual contra un servidor anterior.
    time_zone: z.string().nullable().optional(),
    utc_offset_minutes: z.number().nullable().optional(),
});

export type OdometerExceptionQueueRow = z.infer<
    typeof odometerExceptionQueueRowSchema
>;

/** Cómo se lee un decimal del servidor sin arrastrar la representación. */
export const readingAsNumber = (
    value: string | number | null | undefined,
): number | null => {
    if (value === null || value === undefined) return null;
    const numero = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(numero) ? numero : null;
};
