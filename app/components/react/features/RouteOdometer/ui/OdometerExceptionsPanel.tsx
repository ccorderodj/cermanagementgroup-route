import { useCallback, useEffect, useState } from 'react';
import {
    Badge,
    Button,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/shared/ui/shadcn/new-york';
import { normalizeApiError } from '@/shared/api';
import {
    approveOdometerException,
    fetchPendingOdometerExceptions,
    ODOMETER_REASON_LABELS,
    rejectOdometerException,
    type OdometerExceptionQueueRow,
} from '@/entities/RouteOdometer';

/**
 * La cola de excepciones de odómetro.
 *
 * Qué se está decidiendo aquí
 * ----------------------------
 * Un supervisor dice que no pudo fotografiar el cuentakilómetros y pide teclear
 * la lectura. Aprobar **no escribe ninguna lectura**: abre una única puerta para
 * que él escriba la suya, acotada a esa jornada y ese extremo, y se consume al
 * usarse. Rechazar le devuelve a la foto y deja el viaje bloqueado.
 *
 * Por eso la tabla enseña nombre y vehículo y no identificadores: aprobar esto
 * es un juicio sobre una persona y una situación, y una lista de números empuja
 * a pulsar "aprobar" sin mirar.
 *
 * Inicio y cierre no son lo mismo
 * --------------------------------
 * Una excepción de inicio bloquea a alguien que quiere salir **ahora**; una de
 * cierre pertenece a un día que probablemente ya terminó, porque la Opción B
 * deja cerrar la jornada con la solicitud aún sin revisar. La columna lo dice
 * con palabras para que el orden de atención sea evidente.
 */

function formatearFecha(iso: string): string {
    return new Date(iso).toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
    });
}

const EXTREMOS: Record<'start' | 'end', string> = {
    start: 'Start of day',
    end: 'End of day',
};

export function OdometerExceptionsPanel() {
    const [filas, setFilas] = useState<OdometerExceptionQueueRow[]>([]);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState<string | null>(null);
    // El identificador de la solicitud que se está decidiendo, para que sólo se
    // deshabilite su fila y no la tabla entera.
    const [decidiendo, setDecidiendo] = useState<number | null>(null);

    const cargar = useCallback(async () => {
        setCargando(true);
        try {
            setFilas(await fetchPendingOdometerExceptions());
            setError(null);
        } catch (err) {
            setError(normalizeApiError(err).message);
        } finally {
            setCargando(false);
        }
    }, []);

    useEffect(() => {
        cargar();
    }, [cargar]);

    const decidir = async (id: number, aprobar: boolean) => {
        setDecidiendo(id);
        setError(null);
        try {
            if (aprobar) {
                await approveOdometerException(id);
            } else {
                await rejectOdometerException(id);
            }
            await cargar();
        } catch (err) {
            setError(normalizeApiError(err).message);
            // Se recarga igual: si otra persona la decidió primero, la fila ya
            // no está pendiente y dejarla en pantalla invitaría a reintentarlo.
            await cargar();
        } finally {
            setDecidiendo(null);
        }
    };

    return (
        <div className="flex flex-col gap-4" data-testid="OdometerExceptionsPanel">
            {error && (
                <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                    {error}
                </p>
            )}

            {cargando && (
                <p className="py-8 text-center text-sm text-muted-foreground">
                    Loading…
                </p>
            )}

            {!cargando && filas.length === 0 && (
                <p
                    data-testid="OdometerExceptionsEmpty"
                    className="py-8 text-center text-sm text-muted-foreground"
                >
                    Nothing waiting for review.
                </p>
            )}

            {!cargando && filas.length > 0 && (
                <div className="rounded-md border border-border">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Supervisor</TableHead>
                                <TableHead>Vehicle</TableHead>
                                <TableHead>Reading</TableHead>
                                <TableHead>Reason</TableHead>
                                <TableHead>Requested</TableHead>
                                <TableHead className="text-right">Decision</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {filas.map((fila) => (
                                <TableRow key={fila.id}>
                                    <TableCell className="font-medium">
                                        {fila.requested_by_name}
                                    </TableCell>
                                    <TableCell>
                                        {/* Sin unidad no se inventa un guion
                                            decorativo: se dice que no consta. */}
                                        {fila.vehicle_unit ?? (
                                            <span className="text-muted-foreground">
                                                Not recorded
                                            </span>
                                        )}
                                    </TableCell>
                                    <TableCell>
                                        <Badge
                                            variant={
                                                fila.evidence_type === 'start'
                                                    ? 'default'
                                                    : 'secondary'
                                            }
                                        >
                                            {EXTREMOS[fila.evidence_type]}
                                        </Badge>
                                    </TableCell>
                                    <TableCell>
                                        <span>
                                            {ODOMETER_REASON_LABELS[fila.reason]}
                                        </span>
                                        {fila.reason_note && (
                                            <span className="block text-xs text-muted-foreground">
                                                {fila.reason_note}
                                            </span>
                                        )}
                                    </TableCell>
                                    <TableCell className="text-muted-foreground">
                                        {formatearFecha(fila.requested_at)}
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <div className="flex justify-end gap-2">
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                disabled={decidiendo === fila.id}
                                                onClick={() => decidir(fila.id, false)}
                                            >
                                                Require photo
                                            </Button>
                                            <Button
                                                size="sm"
                                                disabled={decidiendo === fila.id}
                                                onClick={() => decidir(fila.id, true)}
                                            >
                                                Approve
                                            </Button>
                                        </div>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>
            )}

            <p className="text-xs text-muted-foreground">
                Approving lets that supervisor type one reading for that workday,
                once. It records no reading by itself, and the result stays marked
                as entered without a photo.
            </p>
        </div>
    );
}
